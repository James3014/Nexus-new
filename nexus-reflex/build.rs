fn main() -> Result<(), Box<dyn std::error::Error>> {
    tonic_build::configure()
        .build_server(true)
        .compile(
            &["../nexus-swarm/api/proto/swarm.proto"],
            &["../nexus-swarm/api/proto"],
        )?;
    Ok(())
}
