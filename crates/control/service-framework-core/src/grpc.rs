use crate::db;
use crate::metrics::Metrics;
use crate::pb::service_framework_server::ServiceFramework;
use crate::pb::{
    GetServiceRequest, GetServiceResponse, HeartbeatRequest, HeartbeatResponse,
    ListServicesRequest, ListServicesResponse, RegisterServiceRequest,
    RegisterServiceResponse, ServiceState,
};
use crate::validation;
use chrono::{DateTime, Utc};
use sqlx::PgPool;
use std::sync::Arc;
use tonic::{Request, Response, Status};

pub struct ServiceFrameworkGrpc {
    pool: PgPool,
    metrics: Arc<Metrics>,
}

impl ServiceFrameworkGrpc {
    pub fn new(pool: PgPool, metrics: Arc<Metrics>) -> Self {
        Self { pool, metrics }
    }

    fn timestamp_from_chrono(value: DateTime<Utc>) -> prost_types::Timestamp {
        prost_types::Timestamp {
            seconds: value.timestamp(),
            nanos: value.timestamp_subsec_nanos() as i32,
        }
    }
}

#[tonic::async_trait]
impl ServiceFramework for ServiceFrameworkGrpc {
    async fn register_service(
        &self,
        request: Request<RegisterServiceRequest>,
    ) -> Result<Response<RegisterServiceResponse>, Status> {
        let request = request.into_inner();

        let descriptor = request
            .descriptor
            .ok_or_else(|| Status::invalid_argument("descriptor is required"))?;

        let descriptor = validation::normalize_descriptor(descriptor).map_err(Status::from)?;

        let timer = self
            .metrics
            .db_operation_duration_seconds
            .with_label_values(&["register_service"])
            .start_timer();

        let record = db::register_service(&self.pool, &descriptor)
            .await
            .map_err(Status::from)?;

        timer.observe_duration();

        self.metrics
            .registrations_total
            .with_label_values(&[&record.service_name, &record.plane])
            .inc();

        self.metrics
            .active_services
            .with_label_values(&[&record.service_name, &record.plane, &record.state])
            .set(1);

        self.metrics
            .grpc_requests_total
            .with_label_values(&["RegisterService", "OK"])
            .inc();

        Ok(Response::new(RegisterServiceResponse {
            registration_id: record.service_id,
            registered_at: Some(Self::timestamp_from_chrono(record.created_at)),
            state: validation::state_from_db(&record.state),
        }))
    }

    async fn heartbeat(
        &self,
        request: Request<HeartbeatRequest>,
    ) -> Result<Response<HeartbeatResponse>, Status> {
        let request = request.into_inner();

        if request.service_id.trim().is_empty() {
            return Err(Status::invalid_argument("service_id is required"));
        }

        let state = ServiceState::try_from(request.state)
            .map_err(|_| Status::invalid_argument("state is required"))?;

        if state == ServiceState::Unspecified {
            return Err(Status::invalid_argument("state must not be unspecified"));
        }

        let observed_at = request
            .observed_at
            .and_then(|timestamp| {
                DateTime::<Utc>::from_timestamp(timestamp.seconds, timestamp.nanos as u32)
            })
            .unwrap_or_else(Utc::now);

        let timer = self
            .metrics
            .db_operation_duration_seconds
            .with_label_values(&["heartbeat"])
            .start_timer();

        let record = db::record_heartbeat(
            &self.pool,
            &request.service_id,
            request.state,
            &request.detail,
            observed_at,
        )
        .await
        .map_err(Status::from)?;

        timer.observe_duration();

        self.metrics
            .heartbeats_total
            .with_label_values(&[&record.service_name, &record.plane, &record.state])
            .inc();

        self.metrics
            .active_services
            .with_label_values(&[&record.service_name, &record.plane, &record.state])
            .set(1);

        self.metrics
            .grpc_requests_total
            .with_label_values(&["Heartbeat", "OK"])
            .inc();

        Ok(Response::new(HeartbeatResponse {
            acknowledged_at: Some(Self::timestamp_from_chrono(Utc::now())),
            state: validation::state_from_db(&record.state),
        }))
    }

    async fn get_service(
        &self,
        request: Request<GetServiceRequest>,
    ) -> Result<Response<GetServiceResponse>, Status> {
        let request = request.into_inner();

        if request.service_id.trim().is_empty() {
            return Err(Status::invalid_argument("service_id is required"));
        }

        let timer = self
            .metrics
            .db_operation_duration_seconds
            .with_label_values(&["get_service"])
            .start_timer();

        let maybe_record = db::get_service(&self.pool, &request.service_id)
            .await
            .map_err(Status::from)?;

        timer.observe_duration();

        let record = maybe_record.ok_or_else(|| {
            Status::not_found(format!("service {} not found", request.service_id))
        })?;

        let descriptor = db::record_to_descriptor(&record).map_err(Status::from)?;

        self.metrics
            .grpc_requests_total
            .with_label_values(&["GetService", "OK"])
            .inc();

        Ok(Response::new(GetServiceResponse {
            service: Some(descriptor),
        }))
    }

    async fn list_services(
        &self,
        request: Request<ListServicesRequest>,
    ) -> Result<Response<ListServicesResponse>, Status> {
        let request = request.into_inner();

        let environment = if request.environment.trim().is_empty() {
            None
        } else {
            Some(request.environment.trim().to_string())
        };

        let plane = if request.plane == 0 {
            None
        } else {
            Some(
                validation::plane_to_db(request.plane)
                    .map_err(Status::from)?
                    .to_string(),
            )
        };

        let limit = if request.limit <= 0 || request.limit > 1000 {
            100
        } else {
            request.limit
        };

        let offset = if request.offset < 0 { 0 } else { request.offset };

        let timer = self
            .metrics
            .db_operation_duration_seconds
            .with_label_values(&["list_services"])
            .start_timer();

        let (records, total) =
            db::list_services(&self.pool, environment, plane, limit, offset)
                .await
                .map_err(Status::from)?;

        timer.observe_duration();

        let mut services = Vec::with_capacity(records.len());

        for record in records {
            services.push(db::record_to_descriptor(&record).map_err(Status::from)?);
        }

        self.metrics
            .grpc_requests_total
            .with_label_values(&["ListServices", "OK"])
            .inc();

        Ok(Response::new(ListServicesResponse { services, total }))
    }
}