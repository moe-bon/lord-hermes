use crate::config::Upstream;
use serde::Serialize;
use std::collections::BTreeMap;

#[derive(Debug, Clone)]
pub struct RouteRegistry {
    upstreams: BTreeMap<String, Upstream>,
}

#[derive(Debug, Serialize)]
pub struct RouteSummary {
    pub service_name: String,
    pub plane: String,
    pub path_prefix: String,
    pub upstream_base: String,
}

impl RouteRegistry {
    pub fn new(upstreams: Vec<Upstream>) -> Self {
        let mut map = BTreeMap::new();

        for upstream in upstreams {
            map.insert(upstream.service_name.clone(), upstream);
        }

        Self { upstreams: map }
    }

    pub fn get(&self, service_name: &str) -> Option<&Upstream> {
        self.upstreams.get(service_name)
    }

    pub fn services(&self) -> impl Iterator<Item = &Upstream> {
        self.upstreams.values()
    }

    pub fn summary(&self) -> Vec<RouteSummary> {
        self.upstreams
            .values()
            .map(|upstream| RouteSummary {
                service_name: upstream.service_name.clone(),
                plane: upstream.plane.clone(),
                path_prefix: format!("/api/{}", upstream.service_name),
                upstream_base: upstream.base_url.to_string(),
            })
            .collect()
    }
}