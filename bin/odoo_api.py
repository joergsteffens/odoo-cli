#!/usr/bin/env python

import logging
import requests
import json
import sys
from pathlib import Path
from pprint import pprint, pformat

try:
    import configargparse as argparse
except ImportError:
    import argparse


class ParseKwargs(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, dict())
        for value in values:
            key, val = value.split("=")
            getattr(namespace, self.dest)[key] = val


def type_directory(path):
    directory = Path(path)
    if not directory.is_dir():
        raise argparse.ArgumentTypeError("must be a existing directory")
    return directory


def getArgparser():
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

    create = subparsers.add_parser(
        "create",
        help="Create new odoo objects.",
        description='Example: odoo_api.py create res.partner --args name="Example User" email="example.user@example.com"',
    )
    create.add_argument("model", **model_argument_kw)
    create.add_argument(
        "--args",
        nargs="+",
        action=ParseKwargs,
        metavar="key=value",
        help="Parameter for the create command, as key-value pairs.",
    )

    get_customers = subparsers.add_parser("customers")

    get_active_subscriptions = subparsers.add_parser("active_subscriptions")

    get_subscription_credentials = subparsers.add_parser("subscription_credentials")

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

    get_support_customers = subparsers.add_parser("support_customers")

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
        help="Output in JSON format.",
    )

    return argparser


class odoo_api:
    def __init__(self, baseurl, api_key, db=None):
        self.logger = logging.getLogger()
        self.baseurl = baseurl
        self.apiurl = baseurl + "/json/2"
        self.api_key = api_key
        self.db = db
        self.headers = {
            "User-Agent": "odoo-api " + requests.utils.default_user_agent(),
            "Authorization": f"bearer {self.api_key}",
        }
        if self.db:
            self.headers["X-Odoo-Database"] = self.db

    def call(self, baseurl, odoo_model, odoo_method, *args, **kwargs):
        # AFAIK, the odoo json2 API uses named parameter,
        # not no args without name.
        # Still, keep args as parameter for completeness.
        if args:
            raise RuntimeError(f"args given ({args}), but not expected.")

        data = {}
        if kwargs:
            data = kwargs.copy()

        response = requests.post(
            f"{baseurl}/{odoo_model}/{odoo_method}",
            headers=self.headers,
            json=data,
        )
        response.raise_for_status()
        return response.json()

    def json2(self, odoo_model, odoo_method, **kwargs):
        return self.call(self.apiurl, odoo_model, odoo_method, **kwargs)

    def get_version(self, args):
        # does not work, neither as json2, nor as direct call.
        return self.json2(
            "web",
            "version",
        )

    def get_databases(self, args):
        # does not require authentication.
        # call returns a jsonrpc dict. We only care about result.
        return self.call(self.baseurl, "web", "database/list")["result"]

    def get_user_context(self, args):
        return self.json2("res.users", "context_get")
        # show res.users 2 -> "display_name"

    def get_customers(self, args):
        return self.json2(
            "res.partner",
            "search_read",
            domain=[["customer_rank", ">", 0]],
            fields=["name", "email"],
            limit=10,
        )

    def get_active_subscriptions(self, args):
        return self.json2("res.partner", "get_active_subscriptions_api")

    def get_subscription_credentials(self, args):
        return self.json2(
            "res.partner",
            "get_subscription_credentials_api",
            evaluation=args.evaluation,
        )

    def get_support_customers(self, args):
        return self.json2(
            "res.partner",
            "get_support_customers_api",
        )

    def _dump(self, model, domain=None, fields=None, order=None):
        if domain:
            mydomain = domain
        else:
            mydomain = []
        return self.json2(
            model,
            "search_read",
            domain=mydomain,
            fields=fields,
            order=order,
        )

    def search_list(self, args):
        return self._dump(
            args.model,
            fields=["id", "name", "display_name"],
            order="id ASC",
        )

    def dump(self, args):
        return self._dump(args.model)

    def show(self, args):
        # not working:
        # return self.execute_kw(
        #     args.model,
        #     "read",
        #     [[ args.id ]],
        #     #{"fields": ["name"]},
        # )
        result = self._dump(
            args.model,
            domain=[["id", "=", args.id]],
        )

        if args.verbose:
            return result
        return [
            {k: v for k, v in record.items() if v not in ("", [], None, 0, 0.0)}
            for record in result
        ]

    def reinit(self, args):
        return self.json2(
            args.model,
            "recompute_fields",
        )

    def create(self, args):
        model = args.model
        vals_list = [args.args]
        self.logger.debug(f"{model}/create(vals_list={vals_list})")
        return self.json2(model, "create", vals_list=vals_list)

    def mail_add(self, args):
        model = args.model
        message = args.email.read()
        return self.json2(
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

    def config_dump(self, args):
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
            except requests.exceptions.HTTPError as exp:
                self.logger.error(f"{model}: failed: {exp}")
            else:
                result = self._cleanup_dump_data(model, data)
                if args.output_directory:
                    filename = model + ".json"
                    path = args.output_directory / filename
                    self.logger.info(f"path={path}")
                    with path.open("w") as f:
                        if args.json:
                            f.write(json.dumps(result, indent=4))
                        else:
                            f.write(pformat(result))
                else:
                    print(f"### {model}")
                    if args.json:
                        print(json.dumps(result, indent=4))
                    else:
                        pprint(result)

        return True


if __name__ == "__main__":
    logging.basicConfig(
        format="%(levelname)s %(module)s.%(funcName)s: %(message)s", level=logging.INFO
    )
    logger = logging.getLogger()

    parser = getArgparser()
    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)

    # if (not args.database) and (not args.db_name_endpoint_token):
    #     parser.error(
    #         "At least one of --database or --db_name_endpoint_token is required"
    #     )

    database = args.database
    # if not database and args.db_name_endpoint_token:
    #     logger.debug("try to detect database")
    #     database = get_db_name(args.url, args.db_name_endpoint_token)
    #     logger.debug(f"using database: {database}")

    odoo = odoo_api(args.url, args.apikey, database)

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
    }

    if args.command in method_map:
        result = method_map[args.command](args)
        pprint(result)
    else:
        # raise RuntimeError(f"unsupported command {args.command}")
        print(f"unsupported command '{args.command}'\n")
        parser.print_help()
