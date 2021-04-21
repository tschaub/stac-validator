#!/usr/bin/env python

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

__version__ = "2.0.0"

with open("README.md", "r") as fh:
    long_description = fh.read()

extra_reqs = {
    "test": ["pytest"],
}

setup(
    name="stac_validator",
    version=__version__,
    author="James Banting, Darren Wiens, Jonathan Healy",
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
    download_url="https://github.com/sparkgeo/stac-validator/archive/v2.0.0.tar.gz",
    install_requires=[
        "requests>=2.19.1",
        "pytest==6.2.2",
        "jsonschema==3.2.0",
        "pystac==0.5.6",
        "click==7.1.2",
        "pre-commit==1.21.0",
        "tox==3.23.0",
    ],
    packages=["stac_validator"],
    entry_points={
        "console_scripts": ["stac_validator = stac_validator.stac_validator:main"]
    },
    tests_require=["pytest"],
)
