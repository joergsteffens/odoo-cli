#!/usr/bin/env python

import logging
import inspect
import json
import sys
from pathlib import Path
from pprint import pprint, pformat

import requests

try:
    import configargparse as argparse
except ImportError:
    import argparse


class ParseKwargs(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, {})
        for value in values:
            key, val = value.split("=")
            getattr(namespace, self.dest)[key] = val


def parse_json_input(value):
    """Parse JSON from string, file, or stdin"""
    if value == "-":
        # Read from stdin
        return json.load(sys.stdin)

    # Check if it's a file
    if Path(value).is_file():
        with open(value, "r") as f:
            return json.load(f)

    # Parse as JSON string
    try:
        return json.loads(value)
    except json.JSONDecodeError as e:
        raise argparse.ArgumentTypeError(f"Invalid JSON: {e}")


def type_directory(path):
    directory = Path(path)
    if not directory.is_dir():
        raise argparse.ArgumentTypeError("must be a existing directory")
    return directory


def get_argparser():
    argparser = argparse.ArgumentParser(
        description="odoo api.", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    if "configargparse" in sys.modules:
        argparser.add_argument(
            "-c", "--config", is_config_file=True, help="Config file path."
        )
    argparser.add_argument(
        "-d", "--debug", action="store_true", help="enable debugging output"
    )
    argparser.add_argument(
        "-v", "--verbose", action="store_true", help="verbose output"
    )
    argparser.add_argument(
        "--url", default="https://bareos.odoo.com", help="URL of odoo server"
    )
    argparser.add_argument("--database", "--db", help="odoo database")
    argparser.add_argument("--apikey", required=True, help="odoo api key")

    model_argument_kw = {
        "help": "Odoo model, e.g. res.users, res.partner, crm.lead, ..."
    }

    subparsers = argparser.add_subparsers(dest="command")

    identity = subparsers.add_parser("identity", help="Who am I?")

    databases = subparsers.add_parser("databases", help="Show available databases.")

    search_list = subparsers.add_parser("list", help="List objects of a resource.")
    search_list.add_argument("model", **model_argument_kw)

    show = subparsers.add_parser("show", help="Show a single odoo object.")
    show.add_argument("model", **model_argument_kw)
    show.add_argument("id")

    dump = subparsers.add_parser("dump", help="Dump a resource.")
    dump.add_argument("model", **model_argument_kw)

    reinit = subparsers.add_parser(
        "reinit", help="Let odoo recalculate some internal fields."
    )
    reinit.add_argument("model", **model_argument_kw)

    create_description = """
    Example:
    %(prog)s res.partner --args name="Example User" email="example.user@example.com"
    """
    create = subparsers.add_parser(
        "create",
        help="Create a new odoo object.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=create_description,
    )
    create.add_argument("model", **model_argument_kw)
    create.add_argument(
        "--args",
        nargs="+",
        action=ParseKwargs,
        metavar="key=value",
        help="Parameter for the create command, as key-value pairs.",
    )

    get_customers = subparsers.add_parser(
        "customers", help="List all current customers."
    )

    get_active_subscriptions = subparsers.add_parser(
        "active_subscriptions", help="List all active subscriptions."
    )

    get_subscription_credentials = subparsers.add_parser(
        "subscription_credentials",
        help="Show current credentials of active subscriptions.",
    )

    # use this instead of action=BooleanOptionalAction,
    # as it also has to work with Python 3.6 (support.bareos.com, vtiger)
    get_subscription_credentials_evaluation = (
        get_subscription_credentials.add_mutually_exclusive_group()
    )
    get_subscription_credentials_evaluation.add_argument(
        "--evaluation",
        action="store_true",
        help="Credentials only for evaluation subscriptions (default: both)",
        default=None,
    )
    get_subscription_credentials_evaluation.add_argument(
        "--no-evaluation",
        action="store_false",
        dest="evaluation",
        help="Credentials only for normal subscriptions (without evaluation subscriptions)",
        default=None,
    )

    get_support_customers = subparsers.add_parser(
        "support_customers", help="Show all customers with active support contract."
    )

    mail_add = subparsers.add_parser(
        "mail-add", help="Import an email (as file)  into odoo."
    )
    mail_add.add_argument(
        "--model",
        help="Odoo model, into which the emails get processed, e.g. 'crm.lead'. (default: %(default)s)",
        default=False,
    )
    mail_add.add_argument(
        "email",
        type=argparse.FileType("r"),
        help="File containing a full email (extension is often .eml). Use '-' to stdin.",
    )

    config = subparsers.add_parser(
        "config-dump", help="Dump (parts of) the odoo configuration/data."
    )
    config.add_argument(
        "-o",
        "--output-directory",
        type=type_directory,
        metavar="DIRECTORY",
        help="Directory to store config dump files.",
    )
    config.add_argument(
        "--json",
        action="store_true",
        dest="json_format",
        help="Output in JSON format.",
    )

    raw_description = """
    Examples:
    # simple, without parameter:
    %(prog)s res.users context_get
    # with json parameter:
    %(prog)s res.partner search_read --json \'{ "fields": ["id", "name", "display_name"], "order": "id ASC" }\'
    # with mixed json and direct paramter:
    %(prog)s res.partner search_read --json \'{ "fields": ["id", "name", "display_name"] }\' --args order="id ASC"
    # with search domain:
    %(prog)s res.partner search_read --json \'{ "domain": [["name", "ilike", "B%%"]], "fields": ["id", "name", "display_name"], "order": "id ASC" }\'
    """
    raw = subparsers.add_parser(
        "call",
        help="Generic call.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=raw_description,
    )
    raw.add_argument("model", **model_argument_kw)
    raw.add_argument("method", help="Odoo @api.model method to be called.")
    raw.add_argument(
        "--json", type=parse_json_input, help='JSON string, file path, or "-" for stdin'
    )
    raw.add_argument(
        "--args",
        nargs="+",
        action=ParseKwargs,
        metavar="key=value",
        help="Parameter for the method, additional to the JSON structue, as key-value pairs.",
    )

    return argparser


class OdooApi:
    def __init__(self, url, api_key, db=None):
        self.logger = logging.getLogger()
        self.baseurl = url
        self.apiurl = url + "/json/2"
        self.api_key = api_key
        self.db = db
        self.headers = {
            "User-Agent": "odoo_api " + requests.utils.default_user_agent(),
            "Authorization": f"bearer {self.api_key}",
        }
        if self.db:
            self.headers["X-Odoo-Database"] = self.db

    def _call(self, url, odoo_model, odoo_method, **kwargs):
        data = {}
        if kwargs:
            data = kwargs.copy()

        response = requests.post(
            f"{url}/{odoo_model}/{odoo_method}",
            headers=self.headers,
            json=data,
        )
        response.raise_for_status()
        return response.json()

    def call(self, odoo_model, odoo_method, **kwargs):
        return self._call(self.apiurl, odoo_model, odoo_method, **kwargs)

    def get_version(self):
        # does not work, neither as json2, nor as direct call.
        return self.call(
            "web",
            "version",
        )

    def get_databases(self):
        # does not require authentication.
        # call returns a jsonrpc dict. We only care about result.
        return self._call(self.baseurl, "web", "database/list")["result"]

    def get_user_context(self):
        return self.call("res.users", "context_get")
        # show res.users 2 -> "display_name"

    def get_customers(self):
        return self.call(
            "res.partner",
            "search_read",
            domain=[["customer_rank", ">", 0]],
            fields=["name", "email"],
            limit=10,
        )

    def get_active_subscriptions(self):
        return self.call("res.partner", "get_active_subscriptions_api")

    def get_subscription_credentials(self, evaluation=None):
        return self.call(
            "res.partner",
            "get_subscription_credentials_api",
            evaluation=evaluation,
        )

    def get_support_customers(self):
        return self.call(
            "res.partner",
            "get_support_customers_api",
        )

    def _dump(self, model, domain=None, fields=None, order=None):
        if domain:
            mydomain = domain
        else:
            mydomain = []
        return self.call(
            model,
            "search_read",
            domain=mydomain,
            fields=fields,
            order=order,
        )

    def search_list(self, model):
        return self._dump(
            model,
            fields=["id", "name", "display_name"],
            order="id ASC",
        )

    def dump(self, model):
        return self._dump(model)

    def show(self, model, id, verbose):
        # not working:
        # return self.execute_kw(
        #     args.model,
        #     "read",
        #     [[ args.id ]],
        #     #{"fields": ["name"]},
        # )
        result = self._dump(
            model,
            domain=[["id", "=", id]],
        )

        if verbose:
            return result
        return [
            {k: v for k, v in record.items() if v not in ("", [], None, 0, 0.0)}
            for record in result
        ]

    def reinit(self, model):
        return self.call(
            model,
            "recompute_fields",
        )

    def create(self, model, args):
        vals_list = [args]
        self.logger.debug("%s/create(vals_list=%s)", model, str(vals_list))
        return self.call(model, "create", vals_list=vals_list)

    def mail_add(self, model, email):
        message = email.read()
        return self.call(
            "mail.thread",
            "message_process",
            model=model,
            message=message,
        )

    def _cleanup_dump_data(self, model, data):
        # reduce noise (unnecessary changes)
        if model == "account.journal":
            # remove key kanban_dashboard_graph, as this chances on every run.
            for entry in data:
                entry.pop("kanban_dashboard_graph", None)
        elif model == "res.users":
            for entry in data:
                if "fiscal_country_group_codes" in entry:
                    entry["fiscal_country_group_codes"] = sorted(
                        entry["fiscal_country_group_codes"]
                    )
        return data

    def config_dump(self, json_format=None, output_directory=None):
        models = [
            # system parameter
            "ir.config_parameter",
            "ir.module.module",
            # company
            "res.company",
            "res.lang",
            # res.partner:
            #   maybe interesting,
            #   but fields needs to be reduced.
            # "res.partner",
            "res.partner.category",
            "account.account",
            "account.journal",
            "product.category",
            "product.product",
            # "product.template",
            "product.pricelist",
            "product.pricelist.item",
            "sale.order.template",
            "sale.subscription.plan",
            "mail.template",
            # user config
            "res.users",
            "res.users.settings",
            "res.users.apikeys",
            # "res.users.log",
            # empty and should never contain usable data.
            # "res.config.settings",
            # "res.device",
            # "res.device.log",
            # currently not installed:
            # "auditlog.rule",
        ]
        for model in models:
            domain = None
            if model == "ir.module.module":
                # only list installed modules
                domain = [["state", "=", "installed"]]
            order = "id ASC"
            try:
                data = self._dump(model, domain=domain, order=order)
            except requests.exceptions.HTTPError as exc:
                self.logger.error("%s: failed: %s", model, str(exc))
            else:
                result = self._cleanup_dump_data(model, data)
                if output_directory:
                    filename = model + ".json"
                    path = output_directory / filename
                    self.logger.info("path=%s", str(path))
                    with path.open("w") as f:
                        if json_format:
                            f.write(json.dumps(result, indent=4))
                        else:
                            f.write(pformat(result))
                else:
                    print(f"### {model}")
                    if json_format:
                        print(json.dumps(result, indent=4))
                    else:
                        pprint(result)
        return True

    def raw(self, model, method, json=None, args=None):
        kwargs = {}
        if json:
            kwargs.update(json)
        if args:
            # args can overwrite json parameter.
            kwargs.update(args)
        self.logger.debug("%s/%s(%s)", model, method, str(kwargs))
        return self.call(model, method, **kwargs)


def cli_wrapper(method, args):
    sig = inspect.signature(method)
    kwargs = {
        k: v for k, v in vars(args).items() if k in sig.parameters and v is not None
    }
    return method(**kwargs)


if __name__ == "__main__":
    logging.basicConfig(
        format="%(levelname)s %(module)s.%(funcName)s: %(message)s", level=logging.INFO
    )
    logger = logging.getLogger()

    parser = get_argparser()
    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)

    database = args.database
    odoo = OdooApi(args.url, args.apikey, database)

    method_map = {
        "identity": odoo.get_user_context,
        "databases": odoo.get_databases,
        "customers": odoo.get_customers,
        "active_subscriptions": odoo.get_active_subscriptions,
        "subscription_credentials": odoo.get_subscription_credentials,
        "support_customers": odoo.get_support_customers,
        "list": odoo.search_list,
        "show": odoo.show,
        "dump": odoo.dump,
        "reinit": odoo.reinit,
        "create": odoo.create,
        "mail-add": odoo.mail_add,
        "config-dump": odoo.config_dump,
        "call": odoo.raw,
    }

    if args.command in method_map:
        result = cli_wrapper(method_map[args.command], args)
        pprint(result)
    else:
        print(f"unsupported command '{args.command}'\n")
        parser.print_help()
