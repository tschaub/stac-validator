#!/usr/bin/env python3

"""
Description: Validate a STAC item or catalog against the STAC specification.

Usage:
    stac_validator.py <stac_file> [-version] [--verbose] [--timer]

Arguments:
    stac_file  Fully qualified path or url to a STAC file.

Options:
    -v, --version STAC_VERSION   Version to validate against. [default: master]
    -h, --help                   Show this screen.
    --verbose                    Verbose output. [default: False]
"""

__author__ = "James Banting, Alex Mandel, Guillaume Morin, Darren Wiens"

import os
import shutil
from pathlib import Path
import tempfile
from urllib.parse import urljoin
from jsonschema import validate, ValidationError, RefResolutionError, RefResolver
from timeit import default_timer
import traceback
import json
from json.decoder import JSONDecodeError
import requests
from docopt import docopt
import trio
import asks
from cachetools import cached, TTLCache

asks.init("trio")
cache = TTLCache(maxsize=10, ttl=900)


class StacValidate:
    def __init__(self, stac_file, version="master"):
        """
        Validate a STAC file
        :param stac_file: file to validate
        :param version: github tag - defaults to master
        """
        if version is None:
            version = 'master'

        self.stac_version = version
        self.stac_file = stac_file.strip()
        self.dirpath = ''
        self.fetch_specs(self.stac_version)
        self.fpath = Path(stac_file)
        self.message = {}
        self.status = {
            "catalogs": {"valid": 0, "invalid": 0},
            "items": {"valid": 0, "invalid": 0},
        }


    def fetch_specs(self, version):
        """
        Get the versions from github. Cache them if possible.
        :return: specs
        """
        # old versions have a different path to schema
        old_versions = ['v0.4.0', 'v0.4.1', 'v0.5.0', 'v0.5.1', 'v0.5.2']
        geojson_key = "geojson_resolver"
        item_key = "item-{}".format(self.stac_version)
        catalog_key = "catalog-{}".format(self.stac_version)

        if item_key in cache and catalog_key in cache:
            return cache[item_key], cache[geojson_key], cache[catalog_key]

        if version in old_versions:
            CATALOG_SCHEMA_URL = (
                    "https://raw.githubusercontent.com/radiantearth/stac-spec/"
                    + version
                    + "/static-catalog/json-schema/catalog.json"
            )
            ITEM_SCHEMA_URL = (
                    "https://raw.githubusercontent.com/radiantearth/stac-spec/"
                    + version
                    + "/json-spec/json-schema/stac-item.json"
            )
            ITEM_GEOJSON_SCHEMA_URL = (
                    "https://raw.githubusercontent.com/radiantearth/stac-spec/"
                    + version
                    + "/json-spec/json-schema/geojson.json"
            )
        else:
            CATALOG_SCHEMA_URL = (
                    "https://raw.githubusercontent.com/radiantearth/stac-spec/"
                    + version
                    + "/catalog-spec/json-schema/catalog.json"
            )
            ITEM_SCHEMA_URL = (
                    "https://raw.githubusercontent.com/radiantearth/stac-spec/"
                    + version
                    + "/item-spec/json-schema/stac-item.json"
            )
            ITEM_GEOJSON_SCHEMA_URL = (
                    "https://raw.githubusercontent.com/radiantearth/stac-spec/"
                    + version
                    + "/item-spec/json-schema/geojson.json"
            )

        # need to make a temp local file for geojson.
        self.dirpath = tempfile.mkdtemp()

        stac_item_geojson = requests.get(ITEM_GEOJSON_SCHEMA_URL).json()
        stac_item = requests.get(ITEM_SCHEMA_URL).json()
        stac_catalog = requests.get(CATALOG_SCHEMA_URL).json()

        with open(os.path.join(self.dirpath, 'geojson.json'), 'w') as fp:
            geojson_schema = json.dumps(stac_item_geojson)
            fp.write(json.dumps(stac_item_geojson))
            cache[geojson_key] = self.dirpath
            geojson_resolver = RefResolver(
                base_uri="file://{}/".format(self.dirpath), referrer="geojson.json"
            )
        with open(os.path.join(self.dirpath, 'stac-item.json'), 'w') as fp:
            stac_item_schema = json.dumps(stac_item)
            fp.write(stac_item_schema)
            cache[item_key] = stac_item_schema
        with open(os.path.join(self.dirpath, 'stac-catalog.json'), 'w') as fp:
            stac_catalog_schema = json.dumps(stac_catalog)
            fp.write(stac_catalog_schema)
            cache[catalog_key] = stac_catalog_schema

        ITEM_SCHEMA = os.path.join(self.dirpath, 'stac-item.json')
        ITEM_GEOJSON_SCHEMA = os.path.join(self.dirpath, 'geojson.json')
        CATALOG_SCHEMA = os.path.join(self.dirpath, 'stac-catalog.json')

        return ITEM_SCHEMA, ITEM_GEOJSON_SCHEMA, CATALOG_SCHEMA

    def validate_stac(self, stac_file, schema):
        """
        Validate stac
        :param stac_file: input stac_file
        :param schema of STAC (item, catalog)
        :return: validation message
        """

        stac_schema = json.loads(schema)
        try:
            validate(stac_file, stac_schema)
            self.message["valid_stac"] = True
        except RefResolutionError as error:
            # See https://github.com/Julian/jsonschema/issues/362
            # See https://github.com/Julian/jsonschema/issues/313
            # See https://github.com/Julian/jsonschema/issues/98
            try:
                geojson_resolver = cache["geojson_resolver"]
                validate(stac_file, stac_schema, resolver=geosjson_resolver)
                self.message["valid_stac"] = True
            except:
                self.message["valid_stac"] = False
                self.message["error"] = f"{error.args}"
        except ValidationError as error:
            self.message["valid_stac"] = False
            self.message["error"] = f"{error.message} of {list(error.path)}"

        except Exception as error:
            self.message["valid_stac"] = False
            self.message["error"] = f"{error}"

    async def _validate_child(self, child_url, messages):
        stac = StacValidate(child_url.replace("///", "//"), self.stac_version)
        _ = await stac.run()

        messages.append(stac.message)

        self.status["catalogs"]["valid"] += stac.status["catalogs"]["valid"]
        self.status["catalogs"]["invalid"] += stac.status["catalogs"]["invalid"]
        self.status["items"]["valid"] += stac.status["items"]["valid"]
        self.status["items"]["invalid"] += stac.status["items"]["invalid"]

    async def validate_catalog_contents(self):
        """
        Validates contents of current catalog
        :return: list of child messages
        """
        messages = []
        async with trio.open_nursery() as nursery:
            for link in self.stac_file["links"]:
                if link["rel"] in ["child", "item"]:
                    child_url = urljoin(str(self.fpath), link["href"])
                    nursery.start_soon(self._validate_child, child_url, messages)
        return messages

    async def run(self):
        """
        Entry point
        :return: message json
        """
        try:
            resp = await asks.get(self.stac_file)
            self.stac_file = resp.json()
        except requests.exceptions.MissingSchema as e:
            with open(self.stac_file) as f:
                data = json.load(f)
            self.stac_file = data
        except JSONDecodeError as e:
            self.message["valid_stac"] = False
            self.message["error"] = f"{self.stac_file} is not Valid JSON"
            self.status = self.message
            return json.dumps(self.message)

        if "catalog" in self.fpath.stem:
            self.message["asset_type"] = "catalog"
            self.validate_stac(self.stac_file, cache["catalog-{}".format(self.stac_version)])

            if self.message["valid_stac"]:
                self.status["catalogs"]["valid"] += 1
            else:
                self.status["catalogs"]["invalid"] += 1

            self.message["children"] = await self.validate_catalog_contents()
        else:
            self.message["asset_type"] = "item"
            self.validate_stac(self.stac_file, cache["item-{}".format(self.stac_version)])

            if self.message["valid_stac"]:
                self.status["items"]["valid"] += 1
            else:
                self.status["items"]["invalid"] += 1

        self.message["path"] = str(self.fpath)

        return json.dumps(self.message)


async def main(args):
    stac_file = args.get("<stac_file>")
    version = args.get("--version")
    verbose = args.get("--verbose")
    timer = args.get("--timer")

    if timer:
        start = default_timer()

    stac = StacValidate(stac_file, version)
    _ = await stac.run()
    shutil.rmtree(stac.dirpath)

    if verbose:
        print(json.dumps(stac.message, indent=4))
    else:
        print(json.dumps(stac.status, indent=4))

    if timer:
        print('{0:.3f}s'.format(default_timer() - start))


if __name__ == "__main__":
    args = docopt(__doc__)
    try:
        trio.run(main, args)
        retval = 0
    except Exception as e:
        traceback.print_exc()
        retval = -1

    exit(retval)
