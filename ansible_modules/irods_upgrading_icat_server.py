#!/usr/bin/python

import abc
import json
import hashlib
import os
import platform
import socket
import subprocess
import sys
import tempfile
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
        self.module.fail_json(msg='irods_upgrading_icat_server module cannot be used on platform {0}'.format(msg_platform))

class IcatUpgrader(object):
    platform = 'Generic'
    distribution = None
    strategy_class = UnimplementedStrategy
    def __new__(cls, *args, **kwargs):
        return load_platform_subclass(IcatUpgrader, args, kwargs)

    def __init__(self, module):
        self.strategy = self.strategy_class(module)

    def upgrade(self):
        return self.strategy.upgrade()

class GenericStrategy(object):
    __metaclass__ = abc.ABCMeta
    def __init__(self, module):
        self.module = module
        self.irods_packages_root_directory = module.params['irods_packages_root_directory']
        self.icat_database_type = module.params['icat_database_type']

    @property
    def irods_packages_directory(self):
        return os.path.join(self.irods_packages_root_directory, get_irods_platform_string())

    def upgrade(self):
        initial_version = get_irods_version()
        self.stop_server(initial_version)
        self.upgrade_irods_packages()
        final_version = get_irods_version()
        self.upgrade_core_re(initial_version, final_version)
        self.stop_server(final_version) # some upgrades start the server, and starting a running server fails
        self.start_server(final_version)

    def stop_server(self, irods_version):
        if irods_version <= (4,1):
            self.module.run_command(['sudo', 'su', '-', 'irods', '-c', '/var/lib/irods/iRODS/irodsctl stop'], check_rc=True)
        else:
            self.module.run_command(['sudo', 'su', '-', 'irods', '-c', '/var/lib/irods/irodsctl stop'], check_rc=True)

    def upgrade_irods_packages(self):
        database_plugin = self.get_database_plugin()
        icat_package_basename = filter(lambda x:'irods-icat' in x or 'irods-server' in x, os.listdir(self.irods_packages_directory))[0]
        if 'irods-icat' in icat_package_basename:
            icat_package = os.path.join(self.irods_packages_directory, icat_package_basename)
            install_os_packages_from_files([icat_package, database_plugin])
        elif 'irods-server' in icat_package_basename:
            server_package = os.path.join(self.irods_packages_directory, icat_package_basename)
            runtime_package = server_package.replace('irods-server', 'irods-runtime')
            icommands_package = server_package.replace('irods-server', 'irods-icommands')
            install_os_packages_from_files([runtime_package, icommands_package, server_package, database_plugin])
        else:
            raise RuntimeError('unhandled package name')

    def get_database_plugin(self):
        def package_filter(package_name):
            return bool(re.match('irods-database-plugin-' + self.icat_database_type + '[-_]', package_name))
        database_plugin_basename = filter(package_filter, os.listdir(self.irods_packages_directory))[0]
        database_plugin = os.path.join(self.irods_packages_directory, database_plugin_basename)
        return database_plugin
 
    def upgrade_core_re(self, initial_version, final_version):
        if initial_version < (4,1) and final_version >= (4,1):

            contents = '''
acDeleteUserZoneCollections {
  acDeleteCollByAdminIfPresent("/"++$rodsZoneProxy++"/home",$otherUserName);
  acDeleteCollByAdminIfPresent("/"++$rodsZoneProxy++"/trash/home",$otherUserName);
}
acDeleteCollByAdminIfPresent(*parColl,*childColl) {
  *status=errorcode(msiDeleteCollByAdmin(*parColl,*childColl));
  if(*status!=0 && *status!=-808000) {
    failmsg(*status, "msiDeleteCollByAdmin failed in acDeleteCollByAdminIfPresent")
  }
}
'''
            with tempfile.NamedTemporaryFile(prefix='core.re.prepend') as f:
                f.write(contents)
                f.flush()
                self.module.run_command(['sudo', 'su', '-', '-c', 'cat {0} /etc/irods/core.re > /etc/irods/core.re.updated'.format(f.name)], check_rc=True)
                self.module.run_command(['sudo', 'su', '-', '-c', 'mv /etc/irods/core.re.updated /etc/irods/core.re'], check_rc=True)
                self.module.run_command(['sudo', 'chown', 'irods:irods', '/etc/irods/core.re'], check_rc=True)

    def start_server(self, irods_version):
        if irods_version <= (4,1):
            self.module.run_command(['sudo', 'su', '-', 'irods', '-c', '/var/lib/irods/iRODS/irodsctl start'], check_rc=True)
        else:
            self.module.run_command(['sudo', 'su', '-', 'irods', '-c', '/var/lib/irods/irodsctl start'], check_rc=True)

class CentOS6IcatUpgrader(IcatUpgrader):
    platform = 'Linux'
    distribution = 'Centos'
    strategy_class = GenericStrategy

class CentOS7IcatUpgrader(IcatUpgrader):
    platform = 'Linux'
    distribution = 'Centos linux'
    strategy_class = GenericStrategy

class UbuntuIcatUpgrader(IcatUpgrader):
    platform = 'Linux'
    distribution = 'Ubuntu'
    strategy_class = GenericStrategy

class OpenSUSEIcatUpgrader(IcatUpgrader):
    platform = 'Linux'
    distribution = 'Opensuse '
    strategy_class = GenericStrategy

def main():
    module = AnsibleModule(
        argument_spec = dict(
            irods_packages_root_directory=dict(type='str', required=True),
            icat_database_type=dict(choices=['postgres', 'mysql', 'oracle'], type='str', required=True),
        ),
        supports_check_mode=False,
    )

    upgrader = IcatUpgrader(module)
    upgrader.upgrade()

    result = {}
    result['changed'] = True
    result['complex_args'] = module.params

    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
