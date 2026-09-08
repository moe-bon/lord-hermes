use crate::errors::Error;
use crate::pb::{
    FailClosedPolicy, ServiceDescriptor, ServiceEndpoint, ServicePlane, ServiceState,
};

const EXECUTION_PRIVILEGES: &[&str] = &[
    "BROKER_WRITE",
    "EXECUTION_WRITE",
    "ORDER_SUBMIT",
    "ORDER_MODIFY",
    "ORDER_CANCEL",
];

const AI_FORBIDDEN_PRIVILEGES: &[&str] = &[
    "BROKER_WRITE",
    "EXECUTION_WRITE",
    "ORDER_SUBMIT",
    "ORDER_MODIFY",
    "ORDER_CANCEL",
    "RISK_OVERRIDE",
    "KILL_SWITCH",
    "TRADING_WRITE",
];

pub fn normalize_descriptor(
    mut descriptor: ServiceDescriptor,
) -> Result<ServiceDescriptor, Error> {
    descriptor.service_id = descriptor.service_id.trim().to_string();
    descriptor.service_name = descriptor.service_name.trim().to_string();
    descriptor.version = descriptor.version.trim().to_string();
    descriptor.environment = descriptor.environment.trim().to_string();
    descriptor.description = descriptor.description.trim().to_string();

    descriptor.capabilities = normalize_string_list(descriptor.capabilities);
    descriptor.permissions = normalize_string_list(descriptor.permissions);
    descriptor.dependencies = normalize_string_list(descriptor.dependencies);

    for endpoint in descriptor.endpoints.iter_mut() {
        endpoint.name = endpoint.name.trim().to_string();
        endpoint.protocol = endpoint.protocol.trim().to_ascii_lowercase();
        endpoint.uri = endpoint.uri.trim().to_string();
    }

    descriptor.endpoints.retain(|endpoint| {
        !endpoint.name.is_empty()
            && !endpoint.protocol.is_empty()
            && !endpoint.uri.is_empty()
    });

    if descriptor.service_name.is_empty() {
        return Err(Error::InvalidArgument(
            "service_name must not be empty".into(),
        ));
    }

    if descriptor.version.is_empty() {
        return Err(Error::InvalidArgument("version must not be empty".into()));
    }

    if descriptor.environment.is_empty() {
        return Err(Error::InvalidArgument(
            "environment must not be empty".into(),
        ));
    }

    validate_token("service_name", &descriptor.service_name)?;
    validate_token("version", &descriptor.version)?;
    validate_token("environment", &descriptor.environment)?;

    let expected_service_id = format!(
        "{}:{}:{}",
        descriptor.environment, descriptor.service_name, descriptor.version
    );

    if descriptor.service_id.is_empty() {
        descriptor.service_id = expected_service_id.clone();
    } else if descriptor.service_id != expected_service_id {
        return Err(Error::InvalidArgument(format!(
            "service_id must be deterministic and equal to {expected_service_id}"
        )));
    }

    validate_plane(descriptor.plane)?;
    validate_fail_closed_policy(descriptor.fail_closed_policy)?;
    validate_endpoints(&descriptor.endpoints)?;
    enforce_plane_permission_policy(&descriptor)?;

    Ok(descriptor)
}

fn normalize_string_list(values: Vec<String>) -> Vec<String> {
    let mut normalized: Vec<String> = values
        .into_iter()
        .map(|value| value.trim().to_ascii_uppercase())
        .filter(|value| !value.is_empty())
        .collect();

    normalized.sort();
    normalized.dedup();
    normalized
}

fn validate_token(field: &str, value: &str) -> Result<(), Error> {
    if value.contains(char::is_whitespace) {
        return Err(Error::InvalidArgument(format!(
            "{field} must not contain whitespace"
        )));
    }

    Ok(())
}

fn validate_plane(plane: i32) -> Result<(), Error> {
    let plane = ServicePlane::try_from(plane)
        .map_err(|_| Error::InvalidArgument("unknown service plane".into()))?;

    if plane == ServicePlane::Unspecified {
        return Err(Error::InvalidArgument(
            "service plane must be specified".into(),
        ));
    }

    Ok(())
}

fn validate_fail_closed_policy(policy: i32) -> Result<(), Error> {
    let policy = FailClosedPolicy::try_from(policy)
        .map_err(|_| Error::InvalidArgument("unknown fail-closed policy".into()))?;

    if policy == FailClosedPolicy::Unspecified {
        return Err(Error::InvalidArgument(
            "fail_closed_policy must be specified".into(),
        ));
    }

    Ok(())
}

fn validate_endpoints(endpoints: &[ServiceEndpoint]) -> Result<(), Error> {
    for endpoint in endpoints {
        if endpoint.port < 0 || endpoint.port > 65535 {
            return Err(Error::InvalidArgument(format!(
                "endpoint {} has invalid port",
                endpoint.name
            )));
        }

        let protocol_allowed = matches!(
            endpoint.protocol.as_str(),
            "http" | "https" | "grpc" | "tcp" | "udp"
        );

        if !protocol_allowed {
            return Err(Error::InvalidArgument(format!(
                "endpoint {} has unsupported protocol {}",
                endpoint.name, endpoint.protocol
            )));
        }
    }

    Ok(())
}

fn enforce_plane_permission_policy(descriptor: &ServiceDescriptor) -> Result<(), Error> {
    let plane = ServicePlane::try_from(descriptor.plane)
        .map_err(|_| Error::InvalidArgument("unknown service plane".into()))?;

    for permission in &descriptor.permissions {
        if matches!(plane, ServicePlane::Ai | ServicePlane::DataResearch)
            && AI_FORBIDDEN_PRIVILEGES.contains(&permission.as_str())
        {
            return Err(Error::InvalidArgument(format!(
                "AI/research plane may not hold privileged permission {permission}"
            )));
        }

        if EXECUTION_PRIVILEGES.contains(&permission.as_str()) && plane != ServicePlane::Risk {
            return Err(Error::InvalidArgument(format!(
                "only RISK plane may hold execution permission {permission}"
            )));
        }

        if permission == "RISK_OVERRIDE" && plane != ServicePlane::Risk {
            return Err(Error::InvalidArgument(
                "RISK_OVERRIDE is restricted to RISK plane".into(),
            ));
        }

        if permission == "KILL_SWITCH"
            && !matches!(plane, ServicePlane::Risk | ServicePlane::Control)
        {
            return Err(Error::InvalidArgument(
                "KILL_SWITCH is restricted to RISK or CONTROL plane".into(),
            ));
        }
    }

    Ok(())
}

pub fn plane_to_db(plane: i32) -> Result<&'static str, Error> {
    let plane = ServicePlane::try_from(plane)
        .map_err(|_| Error::InvalidArgument("unknown service plane".into()))?;

    match plane {
        ServicePlane::Unspecified => Err(Error::InvalidArgument("plane unspecified".into())),
        ServicePlane::Control => Ok("CONTROL"),
        ServicePlane::MarketData => Ok("MARKET_DATA"),
        ServicePlane::Trading => Ok("TRADING"),
        ServicePlane::Risk => Ok("RISK"),
        ServicePlane::Ai => Ok("AI"),
        ServicePlane::DataResearch => Ok("DATA_RESEARCH"),
        ServicePlane::Observability => Ok("OBSERVABILITY"),
    }
}

pub fn plane_from_db(value: &str) -> i32 {
    match value {
        "CONTROL" => ServicePlane::Control as i32,
        "MARKET_DATA" => ServicePlane::MarketData as i32,
        "TRADING" => ServicePlane::Trading as i32,
        "RISK" => ServicePlane::Risk as i32,
        "AI" => ServicePlane::Ai as i32,
        "DATA_RESEARCH" => ServicePlane::DataResearch as i32,
        "OBSERVABILITY" => ServicePlane::Observability as i32,
        _ => ServicePlane::Unspecified as i32,
    }
}

pub fn plane_i32_from_str(value: &str) -> Result<i32, Error> {
    match value.trim().to_ascii_uppercase().as_str() {
        "CONTROL" => Ok(ServicePlane::Control as i32),
        "MARKET_DATA" => Ok(ServicePlane::MarketData as i32),
        "TRADING" => Ok(ServicePlane::Trading as i32),
        "RISK" => Ok(ServicePlane::Risk as i32),
        "AI" => Ok(ServicePlane::Ai as i32),
        "DATA_RESEARCH" => Ok(ServicePlane::DataResearch as i32),
        "OBSERVABILITY" => Ok(ServicePlane::Observability as i32),
        _ => Err(Error::InvalidArgument(format!("unknown plane {value}"))),
    }
}

pub fn state_to_db(state: i32) -> Result<&'static str, Error> {
    let state = ServiceState::try_from(state)
        .map_err(|_| Error::InvalidArgument("unknown service state".into()))?;

    match state {
        ServiceState::Unspecified => Err(Error::InvalidArgument("state unspecified".into())),
        ServiceState::Starting => Ok("STARTING"),
        ServiceState::Ready => Ok("READY"),
        ServiceState::Degraded => Ok("DEGRADED"),
        ServiceState::Stopping => Ok("STOPPING"),
        ServiceState::Failed => Ok("FAILED"),
    }
}

pub fn state_from_db(value: &str) -> i32 {
    match value {
        "STARTING" => ServiceState::Starting as i32,
        "READY" => ServiceState::Ready as i32,
        "DEGRADED" => ServiceState::Degraded as i32,
        "STOPPING" => ServiceState::Stopping as i32,
        "FAILED" => ServiceState::Failed as i32,
        _ => ServiceState::Unspecified as i32,
    }
}

pub fn state_i32_from_str(value: &str) -> Result<i32, Error> {
    match value.trim().to_ascii_uppercase().as_str() {
        "STARTING" => Ok(ServiceState::Starting as i32),
        "READY" => Ok(ServiceState::Ready as i32),
        "DEGRADED" => Ok(ServiceState::Degraded as i32),
        "STOPPING" => Ok(ServiceState::Stopping as i32),
        "FAILED" => Ok(ServiceState::Failed as i32),
        _ => Err(Error::InvalidArgument(format!("unknown state {value}"))),
    }
}

pub fn policy_to_db(policy: i32) -> Result<&'static str, Error> {
    let policy = FailClosedPolicy::try_from(policy)
        .map_err(|_| Error::InvalidArgument("unknown fail-closed policy".into()))?;

    match policy {
        FailClosedPolicy::Unspecified => {
            Err(Error::InvalidArgument("policy unspecified".into()))
        }
        FailClosedPolicy::ReadOnly => Ok("READ_ONLY"),
        FailClosedPolicy::CancelOpenOrders => Ok("CANCEL_OPEN_ORDERS"),
        FailClosedPolicy::HaltTrading => Ok("HALT_TRADING"),
        FailClosedPolicy::Shutdown => Ok("SHUTDOWN"),
    }
}

pub fn policy_from_db(value: &str) -> i32 {
    match value {
        "READ_ONLY" => FailClosedPolicy::ReadOnly as i32,
        "CANCEL_OPEN_ORDERS" => FailClosedPolicy::CancelOpenOrders as i32,
        "HALT_TRADING" => FailClosedPolicy::HaltTrading as i32,
        "SHUTDOWN" => FailClosedPolicy::Shutdown as i32,
        _ => FailClosedPolicy::Unspecified as i32,
    }
}

pub fn policy_i32_from_str(value: &str) -> Result<i32, Error> {
    match value.trim().to_ascii_uppercase().as_str() {
        "READ_ONLY" => Ok(FailClosedPolicy::ReadOnly as i32),
        "CANCEL_OPEN_ORDERS" => Ok(FailClosedPolicy::CancelOpenOrders as i32),
        "HALT_TRADING" => Ok(FailClosedPolicy::HaltTrading as i32),
        "SHUTDOWN" => Ok(FailClosedPolicy::Shutdown as i32),
        _ => Err(Error::InvalidArgument(format!("unknown policy {value}"))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn base_descriptor() -> ServiceDescriptor {
        ServiceDescriptor {
            service_id: String::new(),
            service_name: "test-service".into(),
            version: "0.1.0".into(),
            environment: "sandbox".into(),
            plane: ServicePlane::Control as i32,
            fail_closed_policy: FailClosedPolicy::Shutdown as i32,
            description: "test".into(),
            capabilities: vec![],
            permissions: vec![],
            endpoints: vec![],
            dependencies: vec![],
        }
    }

    #[test]
    fn normalizes_service_id_deterministically() {
        let descriptor = base_descriptor();
        let normalized = normalize_descriptor(descriptor).expect("descriptor should normalize");

        assert_eq!(normalized.service_id, "sandbox:test-service:0.1.0");
    }

    #[test]
    fn rejects_empty_service_name() {
        let mut descriptor = base_descriptor();
        descriptor.service_name = "   ".into();

        let result = normalize_descriptor(descriptor);

        assert!(result.is_err());
    }

    #[test]
    fn rejects_ai_plane_with_broker_write() {
        let mut descriptor = base_descriptor();
        descriptor.plane = ServicePlane::Ai as i32;
        descriptor.permissions = vec!["BROKER_WRITE".into()];

        let result = normalize_descriptor(descriptor);

        assert!(result.is_err());
    }

    #[test]
    fn rejects_trading_plane_with_order_submit() {
        let mut descriptor = base_descriptor();
        descriptor.plane = ServicePlane::Trading as i32;
        descriptor.permissions = vec!["ORDER_SUBMIT".into()];

        let result = normalize_descriptor(descriptor);

        assert!(result.is_err());
    }

    #[test]
    fn allows_risk_plane_with_order_submit() {
        let mut descriptor = base_descriptor();
        descriptor.plane = ServicePlane::Risk as i32;
        descriptor.permissions = vec!["ORDER_SUBMIT".into()];

        let result = normalize_descriptor(descriptor);

        assert!(result.is_ok());
    }

    #[test]
    fn rejects_unspecified_plane() {
        let mut descriptor = base_descriptor();
        descriptor.plane = ServicePlane::Unspecified as i32;

        let result = normalize_descriptor(descriptor);

        assert!(result.is_err());
    }
}