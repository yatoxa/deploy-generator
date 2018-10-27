#!/usr/bin/env python

import os
import sys
import yaml
import shutil
import argparse
import configparser

from itertools import chain
from subprocess import Popen
from mako.template import Template
from collections import OrderedDict


def yaml_dict_order_preserve():

    def _map_representer(dumper, data):
        return dumper.represent_dict(data.items())

    def _map_constructor(loader, node):
        loader.flatten_mapping(node)
        return OrderedDict(loader.construct_pairs(node))

    if yaml.safe_dump is yaml.dump:
        safe_dumper = yaml.dumper.Dumper
        danger_dumper = yaml.dumper.DangerDumper
        safe_loader = yaml.loader.Loader
        danger_loader = yaml.loader.DangerLoader
    else:
        safe_dumper = yaml.dumper.SafeDumper
        danger_dumper = yaml.dumper.Dumper
        safe_loader = yaml.loader.SafeLoader
        danger_loader = yaml.loader.Loader

    yaml.add_representer(dict, _map_representer, Dumper=safe_dumper)
    yaml.add_representer(OrderedDict, _map_representer, Dumper=safe_dumper)
    yaml.add_representer(dict, _map_representer, Dumper=danger_dumper)
    yaml.add_representer(OrderedDict, _map_representer, Dumper=danger_dumper)

    if sys.version_info < (3, 7):
        yaml.add_constructor(
            'tag:yaml.org,2002:map', _map_constructor, Loader=safe_loader
        )
        yaml.add_constructor(
            'tag:yaml.org,2002:map', _map_constructor, Loader=danger_loader
        )


yaml_dict_order_preserve()


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')

EXAMPLE_CONF_FILE = os.path.join(BASE_DIR, 'deploy.yml')

WORKING_DIR = os.getcwd()
DEPLOY_DIR = os.path.join(WORKING_DIR, 'deploy')
CONF_FILE = os.path.join(WORKING_DIR, 'deploy.yml')


class InventoryFileNotFoundError(Exception):
    pass


class PlaybookFileNotFoundError(Exception):
    pass


class ImproperlyConfiguredError(Exception):
    pass


class Config(object):

    def __init__(self, conf_file=None):
        self.conf_file = conf_file or CONF_FILE

        with open(self.conf_file) as conf_file:
            self._config = yaml.safe_load(conf_file)

    def _get_config_section(self, section_name, section_type):
        section = self._config.get(section_name)

        if isinstance(section, section_type):
            return section

        raise TypeError(
            'Section `{name}` in "{file}" must be {type}'.format(
                name=section_name,
                file=self.conf_file,
                type=section_type
            )
        )

    def get_settings(self):
        return self._get_config_section('settings', dict)

    def get_custom_playbooks(self):
        return self._get_config_section('custom_playbooks', dict)

    def get_services(self):
        return self._get_config_section('services', dict)

    def get_environments(self):
        return self._get_config_section('environments', dict)

    def get_groups(self):
        return self._get_config_section('groups', dict)


class BaseAction(object):

    def __init__(self, config):
        self.config = config
        settings = self.config.get_settings()
        self.deploy_dir = settings.get('deploy_dir') or DEPLOY_DIR

    def do(self):
        raise NotImplementedError


class Action(BaseAction):
    playbook_exec_command = 'ansible-playbook'

    def __init__(
            self,
            config,
            environment_name,
            command_name,
            service_name=None,
            **kwargs
    ):
        super(Action, self).__init__(config)

        self.environment_name = environment_name
        self.service_name = service_name
        self.command_name = command_name
        self.kwargs = kwargs

    def resolve_inventory_file_name(self):
        inventory_file_name = 'inventory-%s.ini' % self.environment_name

        if os.path.exists(os.path.join(self.deploy_dir, inventory_file_name)):
            return inventory_file_name

        raise InventoryFileNotFoundError

    def resolve_playbook_file_name(self):
        _, _, files = next(os.walk(self.deploy_dir))
        names = []

        if self.service_name:
            names.append('%s-%s.yml' % (self.command_name, self.service_name))

        names.append('%s-%s.yml' % (self.command_name, self.environment_name))
        names.append('%s.yml' % self.command_name)

        for playbook_name in names:
            if playbook_name in files:
                return playbook_name

        raise PlaybookFileNotFoundError

    def do(self):
        inventory = self.resolve_inventory_file_name()
        playbook = self.resolve_playbook_file_name()
        cmd = [
            self.playbook_exec_command,
            '-i', inventory,
            playbook,
        ]

        with Popen(cmd) as proc:
            sys.stdout.write(proc.stdout.read())


class TrueIndentDumper(yaml.Dumper):

    def increase_indent(self, flow=False, indentless=False):
        return super(TrueIndentDumper, self).increase_indent(
            flow=flow, indentless=False
        )


class Generate(BaseAction):

    def __init__(self, config):
        super(Generate, self).__init__(config)
        settings = self.config.get_settings()

        self.static_dir = settings.get('static_dir') or STATIC_DIR

        templates_dir = settings.get('templates_dir') or TEMPLATES_DIR
        service_templates_dir = os.path.join(
            templates_dir, 'playbooks', 'service'
        )
        _, _, templates = next(os.walk(service_templates_dir))
        self.templates = [
            os.path.join(service_templates_dir, t) for t in templates
        ]

    def cleanup_deploy_dir(self):
        if os.path.exists(self.deploy_dir):
            shutil.rmtree(self.deploy_dir)

        shutil.copytree(self.static_dir, self.deploy_dir)

    def generate_group_vars(self):
        group_vars_all = OrderedDict()

        for service, params in self.config.get_services().items():
            for param, value in params.items():
                group_var_name = '%s_%s' % (service, param)

                if group_var_name in group_vars_all:
                    raise ImproperlyConfiguredError

                group_vars_all[group_var_name] = value

        group_vars_dir = os.path.join(self.deploy_dir, 'group_vars')
        group_vars_all_file_path = os.path.join(group_vars_dir, 'all.yml')

        os.makedirs(group_vars_dir)

        with open(group_vars_all_file_path, 'w') as group_vars_all_file:
            yaml.dump(
                group_vars_all,
                group_vars_all_file,
                Dumper=TrueIndentDumper,
                default_flow_style=False,
                width=120
            )

    def generate_inventories(self):
        common_groups = [
            ('%s:children' % gn, sl)
            for gn, sl in self.config.get_groups().items()
        ]

        for environment, hosts in self.config.get_environments().items():
            inventory = configparser.ConfigParser(allow_no_value=True)

            for group, items in chain(hosts.items(), common_groups):
                if group in inventory:
                    raise ImproperlyConfiguredError

                inventory[group] = {}

                if items:
                    for option in items:
                        inventory.set(group, option)

            inventory_file_path = os.path.join(
                self.deploy_dir, 'inventory-%s.ini' % environment
            )

            with open(inventory_file_path, 'w') as inventory_file:
                inventory.write(inventory_file)

    def generate_playbooks(self):
        for service, context in self.config.get_services().items():
            for template in self.templates:
                playbook_file_path = os.path.join(
                    self.deploy_dir,
                    '{service}-{template}'.format(
                        service=service,
                        template=template.rsplit('/', maxsplit=1)[-1]
                    )
                )

                with open(playbook_file_path, 'w') as playbook:
                    playbook.write(
                        Template(filename=template).render(
                            service=service,
                            **context
                        )
                    )

    def do(self):
        self.cleanup_deploy_dir()
        self.generate_group_vars()
        self.generate_inventories()
        self.generate_playbooks()


class Deploy(object):

    ACTION_CHOICES = OrderedDict(
        init=dict(
            help='Initializes a new deploy environment by creating'
                 ' a deploy.yml file.',
        ),
        generate=dict(
            help='Generates Ansible playbooks.',
        ),
        list=dict(
            help='Shows list of services and possible actions for them.',
        ),
        status=dict(
            help='Shows statuses of a service`s containers.',
        ),
        build=dict(
            help='Builds a service`s containers.',
        ),
        deploy=dict(
            help='Deploys a service`s containers.',
        ),
        start=dict(
            help='Starts a service`s containers.',
        ),
        stop=dict(
            help='Stops a service`s containers.',
        ),
        restart=dict(
            help='Restarts a service`s containers.',
        ),
        upgrade=dict(
            help='Upgrades a service`s containers: stops containers'
                 ' of the previous version and then starts a new ones.',
        ),
        rollback=dict(
            help='Rollback a service`s containers: stops containers'
                 ' of the new version and then starts a previous ones.',
        ),
    )

    @classmethod
    def _init_cmd_args(cls):
        cmd_args_parser = argparse.ArgumentParser()
        cmd_args_parser.add_argument(
            '-v',
            '--version',
            help='Print the version and exit.'
        )
        cmd_args_parser.add_argument(
            '-c',
            '--config',
            help='Configuration file path.'
        )

        action_group = cmd_args_parser.add_mutually_exclusive_group()

        for action, params in cls.ACTION_CHOICES.items():
            action_group.add_argument(action, nargs='?', **params)

        return cmd_args_parser.parse_args()

    @classmethod
    def _parse_cmd_args(cls):
        action = None
        action_args = []
        action_kwargs = {}

        args = cls._init_cmd_args()

        if args.version:
            pass

        config = Config(conf_file=args.config or None)

        return config, action, action_args, action_kwargs

    def __init__(self):
        (
            self.config,
            self.action,
            self.action_args,
            self.action_kwargs,
        ) = self._parse_cmd_args()

    def action_init(self):
        pass

    def action_generate(self):
        return Generate(self.config)

    def action_list(self):
        pass

    def action_status(self):
        pass

    def wrong_action_handler(self):
        pass

    def dispatch(self):
        if self.action in self.ACTION_CHOICES:
            action_handler = getattr(
                self, 'action_{}'.format(self.action), self.wrong_action_handler
            )
        else:
            action_handler = self.wrong_action_handler

        return action_handler()

    @classmethod
    def run(cls):
        try:
            cls().dispatch().do()
        except Exception:
            return 1

        return 0


def main():
    return Deploy.run()


if __name__ == '__main__':
    main()
