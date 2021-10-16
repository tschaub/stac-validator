#!/usr/bin/env python

from setuptools import setup

__version__ = "2.3.1"

with open("README.md", "r") as fh:
    long_description = fh.read()

extra_reqs = {
    "test": ["pytest"],
}

setup(
    name="stac_validator",
    version=__version__,
    author="James Banting, Jonathan Healy",
    author_email="jhealy@sparkgeo.com",
    description="A package to validate STAC files",
    license="MIT",
    classifiers=[
        "Intended Audience :: Information Technology",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.6",
        "Topic :: Scientific/Engineering :: GIS",
    ],
    keywords="STAC validation raster",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/sparkgeo/stac-validator",
    download_url="https://github.com/sparkgeo/stac-validator/archive/v2.3.0.tar.gz",
    install_requires=[
        "requests>=2.19.1",
        "jsonschema>=3.2.0",
        "pystac==0.5.6",
        "click>=8.0.0",
    ],
    packages=["stac_validator"],
    entry_points={
        "console_scripts": ["stac_validator = stac_validator.stac_validator:main"]
    },
    python_requires=">=3.6",
    tests_require=["pytest"],
)
