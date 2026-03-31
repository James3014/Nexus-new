from setuptools import setup, find_packages

setup(
    name="nexus-reflex",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        'nexus_reflex': ['scripts/*'],
    },
    author="Nexus Orchestrator",
    description="High-performance Rust-based AI Physical Interface",
    python_requires='>=3.8',
    install_requires=[],
    entry_points={
        'console_scripts': [
            'nexus-reflex=nexus_reflex.cli:main',
        ],
    },
)
