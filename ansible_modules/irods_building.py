#!/usr/bin/python

import abc
import json
import os
import shutil


def get_distribution_version_major():
    return get_distribution_version().split('.')[0]

def get_target_identifier():
    return get_distribution() + '_' + get_distribution_version_major()

class UnimplementedStrategy(object):
    def __init__(self, module):
        self.module = module
        self.unimplmented_error()

    def build(self):
        self.unimplmented_error()

    def unimplemented_error(self):
        platform = get_platform()
        distribution = get_distribution()
        if distribution is not None:
            msg_platform = '{0} ({1})'.format(platform, distribution)
        else:
            msg_platform = platform
        self.module.fail_json(msg='irods_building module cannot be used on platform {0}'.format(msg_platform))

class Builder(object):
    platform = 'Generic'
    distribution = None
    strategy_class = UnimplementedStrategy
    def __new__(cls, *args, **kwargs):
        return load_platform_subclass(Builder, args, kwargs)

    def __init__(self, module):
        self.strategy = self.strategy_class(module)

    def build(self):
        return self.strategy.build()

class GenericStrategy(object):
    __metaclass__ = abc.ABCMeta
    def __init__(self, module):
        self.module = module
        self.output_root_directory = module.params['output_root_directory']
        self.git_repository = module.params['git_repository']
        self.git_commitish = module.params['git_commitish']
        self.local_irods_git_dir = os.path.expanduser('~/irods')

    @abc.abstractproperty
    def building_dependencies(self):
        pass

    @abc.abstractmethod
    def install_packages(self, packages):
        pass

    @property
    def output_directory(self):
        return os.path.join(self.output_root_directory, get_target_identifier())

    def build(self):
        self.install_building_dependencies()
        self.prepare_git_repository()
        self.build_irods_packages()
        self.copy_build_output()

    def install_building_dependencies(self):
        self.install_packages(self.building_dependencies)

    def prepare_git_repository(self):
        self.module.run_command('git clone --recursive {0} {1}'.format(self.git_repository, self.local_irods_git_dir), check_rc=True)
        self.module.run_command('git checkout {0}'.format(self.git_commitish), cwd=self.local_irods_git_dir, check_rc=True)
        self.module.run_command('git submodule update --init --recursive', cwd=self.local_irods_git_dir, check_rc=True)

    def build_irods_packages(self):
        os.makedirs(os.path.join(self.local_irods_git_dir, 'build'))
        self.module.run_command('sudo ./packaging/build.sh -r icat postgres > ./build/build_output_icat_postgres.log 2>&1', cwd=self.local_irods_git_dir, use_unsafe_shell=True, check_rc=True)
        self.module.run_command('sudo ./packaging/build.sh -r resource postgres > ./build/build_output_resource.log 2>&1', cwd=self.local_irods_git_dir, use_unsafe_shell=True, check_rc=True)
        self.module.run_command('sudo ./packaging/build.sh -r icat mysql > ./build/build_output_icat_mysql.log 2>&1', cwd=self.local_irods_git_dir, use_unsafe_shell=True, check_rc=True)

    def copy_build_output(self):
        shutil.copytree(os.path.join(self.local_irods_git_dir, 'build'), self.output_directory)

class RedHatStrategy(GenericStrategy):
    @property
    def building_dependencies(self):
        return ['python-devel', 'help2man', 'unixODBC', 'fuse-devel', 'curl-devel', 'bzip2-devel', 'zlib-devel', 'pam-devel', 'openssl-devel', 'libxml2-devel', 'krb5-devel', 'unixODBC-devel', 'perl-JSON']

    def install_building_dependencies(self):
        super(RedHatStrategy, self).install_building_dependencies()
        self.install_oracle_dependencies()

    def install_oracle_dependencies(self):
        tar_file = os.path.expanduser('~/oci.tar')
        self.module.run_command(['wget', 'http://people.renci.org/~jasonc/irods/oci.tar', '-O', tar_file], check_rc=True)
        tar_dir = os.path.expanduser('~/oci')
        os.mkdir(tar_dir)
        self.module.run_command(['tar', '-xf', 'oci.tar', '-C', tar_dir], check_rc=True)
        self.module.run_command('sudo rpm -i --nodeps ./oci/*', use_unsafe_shell=True, check_rc=True)

    def build_irods_packages(self):
        super(RedHatStrategy, self).build_irods_packages()
        self.module.run_command('sudo ./packaging/build.sh -r icat oracle > ./build/build_output_icat_oracle.log 2>&1', cwd=self.local_irods_git_dir, use_unsafe_shell=True, check_rc=True)

    def install_packages(self, packages):
        install_command = 'sudo yum install -y {0}'.format(' '.join(packages))
        self.module.run_command(install_command, check_rc=True)

class DebianStrategy(GenericStrategy):
    @property
    def building_dependencies(self):
        return ['git', 'g++', 'make', 'python-dev', 'help2man', 'unixodbc', 'libfuse-dev', 'libcurl4-gnutls-dev', 'libbz2-dev', 'zlib1g-dev', 'libpam0g-dev', 'libssl-dev', 'libxml2-dev', 'libkrb5-dev', 'unixodbc-dev', 'libjson-perl']

    def install_packages(self, packages):
        self.module.run_command('sudo apt-get update', check_rc=True)
        install_command = 'sudo apt-get install -y {0}'.format(' '.join(packages))
        self.module.run_command(install_command, check_rc=True)

class SuseStrategy(GenericStrategy):
    @property
    def building_dependencies(self):
        return ['python-devel', 'help2man', 'unixODBC', 'fuse-devel', 'libcurl-devel', 'libbz2-devel', 'libopenssl-devel', 'libxml2-devel', 'krb5-devel', 'perl-JSON', 'unixODBC-devel']

    def install_packages(self, packages):
        install_command = 'sudo zypper --non-interactive install {0}'.format(' '.join(packages))
        self.module.run_command(install_command, check_rc=True)

class CentOSBuilder(Builder):
    platform = 'Linux'
    distribution = 'Centos'
    strategy_class = RedHatStrategy

class UbuntuBuilder(Builder):
    platform = 'Linux'
    distribution = 'Ubuntu'
    strategy_class = DebianStrategy

class OpenSuseBuilder(Builder):
    platform = 'Linux'
    distribution = 'Opensuse '
    strategy_class = SuseStrategy

def main():
    module = AnsibleModule(
        argument_spec = dict(
            output_root_directory=dict(type='str', required=True),
            git_repository=dict(type='str', required=True),
            git_commitish=dict(type='str', required=True),
        ),
        supports_check_mode=False,
    )

    builder = Builder(module)
    builder.build()

    result = {}
    result['changed'] = True
    result['complex_args'] = module.params

    module.exit_json(**result)


from ansible.module_utils.basic import *
main()
