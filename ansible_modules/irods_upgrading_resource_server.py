#!/usr/bin/python

import abc
import json
import hashlib
import os
import platform
import socket
import subprocess
import sys
import time


class UnimplementedStrategy(object):
    def __init__(self, module):
        self.module = module
        self.unimplmented_error()

    def upgrade(self):
        self.unimplmented_error()

    def unimplemented_error(self):
        platform = get_platform()
        distribution = get_distribution()
        if distribution is not None:
            msg_platform = '{0} ({1})'.format(platform, distribution)
        else:
            msg_platform = platform
        self.module.fail_json(msg='irods_upgrading_resource_server module cannot be used on platform {0}'.format(msg_platform))

class ResourceUpgrader(object):
    platform = 'Generic'
    distribution = None
    strategy_class = UnimplementedStrategy
    def __new__(cls, *args, **kwargs):
        return load_platform_subclass(ResourceUpgrader, args, kwargs)

    def __init__(self, module):
        self.strategy = self.strategy_class(module)

    def upgrade(self):
        return self.strategy.upgrade()

class GenericStrategy(object):
    __metaclass__ = abc.ABCMeta
    def __init__(self, module):
        self.module = module
        self.irods_packages_root_directory = module.params['irods_packages_root_directory']

    @property
    def irods_packages_directory(self):
        return os.path.join(self.irods_packages_root_directory, get_irods_platform_string())

    def upgrade(self):
        self.stop_server()
        self.upgrade_irods_packages()
        self.stop_server() # some upgrades start the server, and starting a running server fails
        self.start_server()

    def stop_server(self):
        self.module.run_command(['sudo', 'su', '-', 'irods', '-c', '/var/lib/irods/iRODS/irodsctl stop'], check_rc=True)

    def upgrade_irods_packages(self):
        resource_package_basename = filter(lambda x:'irods-resource' in x, os.listdir(self.irods_packages_directory))[0]
        resource_package = os.path.join(self.irods_packages_directory, resource_package_basename)
        install_os_packages_from_files([resource_package])

    def start_server(self):
        self.module.run_command(['sudo', 'su', '-', 'irods', '-c', '/var/lib/irods/iRODS/irodsctl start'], check_rc=True)

class CentOS6ResourceUpgrader(ResourceUpgrader):
    platform = 'Linux'
    distribution = 'Centos'
    strategy_class = GenericStrategy

class CentOS7ResourceUpgrader(ResourceUpgrader):
    platform = 'Linux'
    distribution = 'Centos linux'
    strategy_class = GenericStrategy

class UbuntuResourceUpgrader(ResourceUpgrader):
    platform = 'Linux'
    distribution = 'Ubuntu'
    strategy_class = GenericStrategy

class OpenSUSEResourceUpgrader(ResourceUpgrader):
    platform = 'Linux'
    distribution = 'Opensuse '
    strategy_class = GenericStrategy

def main():
    module = AnsibleModule(
        argument_spec = dict(
            irods_packages_root_directory=dict(type='str', required=True),
        ),
        supports_check_mode=False,
    )

    upgrader = ResourceUpgrader(module)
    upgrader.upgrade()

    result = {}
    result['changed'] = True
    result['complex_args'] = module.params

    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
