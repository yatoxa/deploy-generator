#!/usr/bin/env python

import os
import sys
import yaml
import shutil
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


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
DEPLOY_DIR = os.path.join(BASE_DIR, 'deploy')

DEPLOY_PROVIDER = 'ansible'


class InventoryFileNotFoundError(Exception):
    pass


class PlaybookFileNotFoundError(Exception):
    pass


class ImproperlyConfiguredError(Exception):
    pass


class Config(object):
    default_conf_file = os.path.join(BASE_DIR, 'deploy.yml')

    def __init__(self, conf_file=None):
        self.conf_file = conf_file or self.default_conf_file

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

    def get_services(self):
        return self._get_config_section('services', dict)

    def get_environments(self):
        return self._get_config_section('environments', dict)

    def get_groups(self):
        return self._get_config_section('groups', dict)


class Action(object):
    working_dir = os.path.join(BASE_DIR, '..')
    playbook_exec_command = 'ansible-playbook'
    template_name = ''

    def __init__(self, environment_name, command_name, service_name=None, **kwargs):
        self.environment_name = environment_name
        self.service_name = service_name
        self.command_name = command_name
        self.kwargs = kwargs

    def resolve_inventory_file_name(self):
        inventory_file_name = 'inventory-%s.ini' % self.environment_name

        if os.path.exists(os.path.join(self.working_dir, inventory_file_name)):
            return inventory_file_name

        raise InventoryFileNotFoundError

    def resolve_playbook_file_name(self):
        _, _, files = next(os.walk(self.working_dir))
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


class Generate(object):

    def __init__(self, config=None):
        self.config = config or Config()

        settings = self.config.get_settings()
        self.deploy_dir = settings.get('deploy_dir') or DEPLOY_DIR
        self.static_dir = settings.get('static_dir') or STATIC_DIR

        templates_dir = settings.get('templates_dir') or TEMPLATES_DIR
        self.deploy_provider = settings.get('deploy_provider') or DEPLOY_PROVIDER

        service_templates_dir = os.path.join(
            templates_dir, self.deploy_provider, 'playbooks', 'service'
        )

        _, _, templates = next(os.walk(service_templates_dir))
        self.templates = [
            os.path.join(service_templates_dir, t) for t in templates
        ]

    def cleanup_deploy_dir(self):
        if os.path.exists(self.deploy_dir):
            shutil.rmtree(self.deploy_dir)

        shutil.copytree(
            os.path.join(self.static_dir, self.deploy_provider), self.deploy_dir
        )

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
        for name, context in self.config.get_services().items():
            for template in self.templates:
                playbook_file_path = os.path.join(
                    self.deploy_dir,
                    '{service}-{template}'.format(
                        service=name,
                        template=template.rsplit('/', maxsplit=1)[-1]
                    )
                )

                with open(playbook_file_path, 'w') as playbook:
                    playbook.write(
                        Template(filename=template).render(**context)
                    )

    def do(self):
        self.cleanup_deploy_dir()
        self.generate_group_vars()
        self.generate_inventories()
        self.generate_playbooks()


class Deploy(object):
    """
        -v, --version   Print the version and exit.
        -h, --help      Print this help.

        -c, --config    Configuration file path.

    Common commands:
        generate        Generate Ansible playbooks.

        list            Shows list of services and possible actions for them.
        status          Shows statuses of a service`s containers.

        build           Builds a service`s containers.
        deploy          Deploys a service`s containers.
        start           Starts a service`s containers.
        stop            Stops a service`s containers.
        restart         Restarts a service`s containers.
        upgrade         Upgrades a service`s containers: stops containers of
                        the previous version and then starts a new ones.
        rollback        Rollback a service`s containers: stops containers of
                        the new version and then starts a previous ones.
    """

    def __init__(self):
        pass

    def action_list(self):
        pass

    def action_status(self):
        pass

    def run(self):
        pass


def main():
    config = Config()
    Generate(config=config).do()


if __name__ == '__main__':
    main()
