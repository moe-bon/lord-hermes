fn main() -> Result<(), Box<dyn std::error::Error>> {
    let proto_file = "../../../proto/apexquant/common/v1/service_framework.proto";
    let include_dir = "../../../proto";

    tonic_build::configure()
        .build_server(true)
        .build_client(false)
        .compile_protos(&[proto_file], &[include_dir])?;

    println!("cargo:rerun-if-changed={proto_file}");
    Ok(())
}