import json
import os
from json.decoder import JSONDecodeError
from typing import List
from urllib.error import HTTPError, URLError

import click
import jsonschema  # type: ignore
from jsonschema import RefResolver
from requests import exceptions

from .utilities import (
    fetch_and_parse_file,
    get_stac_type,
    link_message,
    set_schema_addr,
)


class StacValidate:
    def __init__(
        self,
        stac_file: str = None,
        recursive: int = -2,
        core: bool = False,
        links: bool = False,
        assets: bool = False,
        extensions: bool = False,
        custom: str = "",
        verbose: bool = False,
        log: str = "",
    ):
        self.stac_file = stac_file
        self.message: list = []
        self.custom = custom
        self.links = links
        self.assets = assets
        self.recursive = recursive
        self.extensions = extensions
        self.core = core
        self.stac_content: dict = {}
        self.version = ""
        self.depth: int = 0
        self.skip_val = False
        self.verbose = verbose
        self.valid = False
        self.log = log

    def create_err_msg(self, err_type: str, err_msg: str) -> dict:
        self.valid = False
        return {
            "version": self.version,
            "path": self.stac_file,
            "schema": [self.custom],
            "valid_stac": False,
            "error_type": err_type,
            "error_message": err_msg,
        }

    def create_message(self, stac_type: str, val_type: str) -> dict:
        return {
            "version": self.version,
            "path": self.stac_file,
            "schema": [self.custom],
            "valid_stac": False,
            "asset_type": stac_type.upper(),
            "validation_method": val_type,
        }

    def assets_val(self) -> dict:
        format_valid: List[str] = []
        format_invalid: List[str] = []
        request_valid: List[str] = []
        request_invalid: List[str] = []
        for _, value in self.stac_content["assets"].items():
            link_message(
                value, request_valid, request_invalid, format_valid, format_invalid
            )

        message = {
            "format_valid": format_valid,
            "format_invalid": format_invalid,
            "request_valid": request_valid,
            "request_invalid": request_invalid,
        }
        return message

    def links_val(self) -> dict:
        format_valid: List[str] = []
        format_invalid: List[str] = []
        request_valid: List[str] = []
        request_invalid: List[str] = []
        root_url = ""
        for link in self.stac_content["links"]:
            if link["rel"] == "self":
                root_url = (
                    link["href"].split("/")[0] + "//" + link["href"].split("/")[2]
                )
        for link in self.stac_content["links"]:
            if link["href"][0:4] != "http":
                link["href"] = root_url + link["href"][1:]
            link_message(
                link, request_valid, request_invalid, format_valid, format_invalid
            )

        message = {
            "format_valid": format_valid,
            "format_invalid": format_invalid,
            "request_valid": request_valid,
            "request_invalid": request_invalid,
        }
        return message

    def extensions_val(self, stac_type: str) -> dict:
        message = self.create_message(stac_type, "extensions")
        message["schema"] = []
        valid = True
        if stac_type == "ITEM":
            try:
                if "stac_extensions" in self.stac_content:
                    # error with the 'proj' extension not being 'projection' in older stac
                    if "proj" in self.stac_content["stac_extensions"]:
                        index = self.stac_content["stac_extensions"].index("proj")
                        self.stac_content["stac_extensions"][index] = "projection"
                    schemas = self.stac_content["stac_extensions"]
                    for extension in schemas:
                        if "http" not in extension:
                            # where are the extensions for 1.0.0-beta.2 on cdn.staclint.com?
                            if self.version == "1.0.0-beta.2":
                                self.stac_content["stac_version"] = "1.0.0-beta.1"
                                self.version = self.stac_content["stac_version"]
                            extension = f"https://cdn.staclint.com/v{self.version}/extension/{extension}.json"
                        self.custom = extension
                        self.custom_val()
                        message["schema"].append(extension)
            except jsonschema.exceptions.ValidationError as e:
                valid = False
                if e.absolute_path:
                    err_msg = f"{e.message}. Error is in {' -> '.join([str(i) for i in e.absolute_path])}"
                else:
                    err_msg = f"{e.message} of the root of the STAC object"
                message = self.create_err_msg("ValidationError", err_msg)
                return message
            except Exception as e:
                valid = False
                err_msg = f"{e}. Error in Extensions."
                return self.create_err_msg("Exception", err_msg)
        else:
            self.core_val(stac_type)
            message["schema"] = [self.custom]
        self.valid = valid
        return message

    def custom_val(self):
        # in case the path to custom json schema is local
        # it may contain relative references
        schema = fetch_and_parse_file(self.custom)
        if os.path.exists(self.custom):
            custom_abspath = os.path.abspath(self.custom)
            custom_dir = os.path.dirname(custom_abspath).replace("\\", "/")
            custom_uri = f"file:///{custom_dir}/"
            resolver = RefResolver(custom_uri, self.custom)
            jsonschema.validate(self.stac_content, schema, resolver=resolver)
        else:
            schema = fetch_and_parse_file(self.custom)
            jsonschema.validate(self.stac_content, schema)

    def core_val(self, stac_type: str):
        stac_type = stac_type.lower()
        self.custom = set_schema_addr(self.version, stac_type.lower())
        self.custom_val()

    def default_val(self, stac_type: str) -> dict:
        message = self.create_message(stac_type, "default")
        message["schema"] = []
        self.core_val(stac_type)
        core_schema = self.custom
        message["schema"].append(core_schema)
        stac_type = stac_type.upper()
        if stac_type == "ITEM":
            message = self.extensions_val(stac_type)
            message["validation_method"] = "default"
            message["schema"].append(core_schema)
        if self.links:
            message["links_validated"] = self.links_val()
        if self.assets:
            message["assets_validated"] = self.assets_val()
        return message

    def recursive_val(self, stac_type: str):
        if self.skip_val is False:
            self.custom = set_schema_addr(self.version, stac_type.lower())
            message = self.create_message(stac_type, "recursive")
            message["valid_stac"] = False
            try:
                _ = self.default_val(stac_type)

            except jsonschema.exceptions.ValidationError as e:
                if e.absolute_path:
                    err_msg = f"{e.message}. Error is in {' -> '.join([str(i) for i in e.absolute_path])}"
                else:
                    err_msg = f"{e.message} of the root of the STAC object"
                message.update(self.create_err_msg("ValidationError", err_msg))
                self.message.append(message)
                return
            message["valid_stac"] = True
            self.message.append(message)
            self.depth = self.depth + 1
            if self.recursive > -1:
                if self.depth >= int(self.recursive):
                    self.skip_val = True
            base_url = self.stac_file
            for link in self.stac_content["links"]:
                if link["rel"] == "child" or link["rel"] == "item":
                    address = link["href"]
                    if "http" not in address:
                        x = str(base_url).split("/")
                        x.pop(-1)
                        st = x[0]
                        for i in range(len(x)):
                            if i > 0:
                                st = st + "/" + x[i]
                        self.stac_file = st + "/" + address
                    else:
                        self.stac_file = address
                    self.stac_content = fetch_and_parse_file(self.stac_file)
                    self.stac_content["stac_version"] = self.version
                    stac_type = get_stac_type(self.stac_content).lower()

                if link["rel"] == "child":

                    if self.verbose is True:
                        click.echo(json.dumps(message, indent=4))
                    self.recursive_val(stac_type)

                if link["rel"] == "item":
                    self.custom = set_schema_addr(self.version, stac_type.lower())
                    message = self.create_message(stac_type, "recursive")
                    if self.version == "0.7.0":
                        schema = fetch_and_parse_file(self.custom)
                        # this next line prevents this: unknown url type: 'geojson.json' ??
                        schema["allOf"] = [{}]
                        jsonschema.validate(self.stac_content, schema)
                    else:
                        msg = self.default_val(stac_type)
                        message["schema"] = msg["schema"]
                    message["valid_stac"] = True

                    if self.log != "":
                        self.message.append(message)
                    if self.recursive < 5:
                        self.message.append(message)
                    if self.verbose is True:
                        click.echo(json.dumps(message, indent=4))

    def validate_dict(cls, stac_content):
        cls.stac_content = stac_content
        return cls.run()

    def run(cls):
        message = {}
        try:
            if cls.stac_file is not None:
                cls.stac_content = fetch_and_parse_file(cls.stac_file)
            stac_type = get_stac_type(cls.stac_content).upper()
            cls.version = cls.stac_content["stac_version"]

            if cls.core is True:
                message = cls.create_message(stac_type, "core")
                cls.core_val(stac_type)
                message["schema"] = [cls.custom]
                cls.valid = True
            elif cls.custom != "":
                message = cls.create_message(stac_type, "custom")
                message["schema"] = [cls.custom]
                cls.custom_val()
                cls.valid = True
            elif cls.recursive > -2:
                cls.recursive_val(stac_type)
                cls.valid = True
            elif cls.extensions is True:
                message = cls.extensions_val(stac_type)
            else:
                cls.valid = True
                message = cls.default_val(stac_type)

        except ValueError as e:
            message.update(cls.create_err_msg("ValueError", str(e)))
        except URLError as e:
            message.update(cls.create_err_msg("URLError", str(e)))
        except JSONDecodeError as e:
            message.update(cls.create_err_msg("JSONDecodeError", str(e)))
        except TypeError as e:
            message.update(cls.create_err_msg("TypeError", str(e)))
        except FileNotFoundError as e:
            message.update(cls.create_err_msg("FileNotFoundError", str(e)))
        except ConnectionError as e:
            message.update(cls.create_err_msg("ConnectionError", str(e)))
        except exceptions.SSLError as e:
            message.update(cls.create_err_msg("SSLError", str(e)))
        except OSError as e:
            message.update(cls.create_err_msg("OSError", str(e)))
        except jsonschema.exceptions.ValidationError as e:
            if e.absolute_path:
                err_msg = f"{e.message}. Error is in {' -> '.join([str(i) for i in e.absolute_path])}"
            else:
                err_msg = f"{e.message} of the root of the STAC object"
            message.update(cls.create_err_msg("ValidationError", err_msg))
        except KeyError as e:
            message.update(cls.create_err_msg("KeyError", str(e)))
        except HTTPError as e:
            message.update(cls.create_err_msg("HTTPError", str(e)))
        except Exception as e:
            message.update(cls.create_err_msg("Exception", str(e)))

        message["valid_stac"] = cls.valid

        if cls.recursive < -1:
            cls.message.append(message)

        if cls.log != "":
            f = open(cls.log, "w")
            f.write(json.dumps(cls.message, indent=4))
            f.close()

        if cls.valid:
            return True
        else:
            return False