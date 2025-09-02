from setuptools import setup, find_packages

setup(
    name="putio-migrator",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "requests>=2.31.0",
        "toml>=0.10.2",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-mock>=3.11.1",
            "pytest-cov>=4.1.0",
            "responses>=0.23.3",
        ]
    },
    python_requires=">=3.8",
)