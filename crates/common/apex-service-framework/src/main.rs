use actix_web::{get, App, HttpServer, HttpResponse};
#[get("/healthz")]
async fn healthz() -> HttpResponse { HttpResponse::Ok().json(serde_json::json!({"status": "ok"})) }
#[get("/metrics")]
async fn metrics() -> HttpResponse { HttpResponse::Ok().body("# metrics\n") }
#[actix_web::main]
async fn main() -> std::io::Result<()> {
    HttpServer::new(|| App::new().service(healthz).service(metrics))
        .bind("0.0.0.0:8080")?.run().await
}
