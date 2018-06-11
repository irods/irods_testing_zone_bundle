#!/usr/bin/python

import abc
import glob
import itertools
import json
import os
import shutil
import tempfile


class UnimplementedStrategy(object):
    def __init__(self, module):
        self.module = module
        self.unimplemented_error()

    def build(self):
        self.unimplemented_error()

    def unimplemented_error(self):
        platform = get_platform()
        distribution = get_distribution()
        if distribution is not None:
            msg_platform = '{0} ({1})'.format(platform, distribution)
        else:
            msg_platform = platform
        self.module.fail_json(msg='irods_externals module cannot be used on platform {0}'.format(msg_platform))

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
        self.local_git_dir = tempfile.mkdtemp(prefix='irods_externals', dir='/tmp') #os.path.expanduser('~/irods_externals')

    @property
    def output_directory(self):
        return os.path.join(self.output_root_directory, get_irods_platform_string())

    def build(self):
        self.prepare_git_repository()
        self.install_dependencies()
        self.setup_build_environment()
        self.build_externals_and_copy_output()

    def prepare_git_repository(self):
        install_os_packages(['git'])
        self.module.run_command(['git', 'clone', '--recursive', self.git_repository, self.local_git_dir], check_rc=True)
        self.module.run_command(['git', 'checkout', self.git_commitish], cwd=self.local_git_dir, check_rc=True)
        self.module.run_command(['git', 'submodule', 'update', '--init', '--recursive'], cwd=self.local_git_dir, check_rc=True)

    def install_dependencies(self):
        self.module.run_command([os.path.join(self.local_git_dir, 'install_prerequisites.py')], check_rc=True)

    def setup_build_environment(self):
        pass

    def build_externals_and_copy_output(self):
        try:
            self.build_externals()
        finally:
            os.makedirs(self.output_directory)
            for f in itertools.chain(glob.glob(self.local_git_dir + '/*.rpm'),
                                     glob.glob(self.local_git_dir + '/*.deb'),
                                     glob.glob(self.local_git_dir + '/*.log'),):
                shutil.copy2(f, self.output_directory)

    def build_externals(self):
        self.module.run_command(['make'], cwd=self.local_git_dir, check_rc=True)

class RedHatStrategy(GenericStrategy):
    def setup_build_environment(self):
        super(RedHatStrategy, self).setup_build_environment()
        if get_distribution_version_major() == '6':
            os.environ['CC'] = '/opt/rh/devtoolset-2/root/usr/bin/gcc'
            os.environ['CXX'] = '/opt/rh/devtoolset-2/root/usr/bin/g++'

class DebianStrategy(GenericStrategy):
    pass

class SuseStrategy(GenericStrategy):
    pass

class CentOS6Builder(Builder):
    platform = 'Linux'
    distribution = 'Centos'
    strategy_class = RedHatStrategy

class CentOS7Builder(Builder):
    platform = 'Linux'
    distribution = 'Centos linux'
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
    result['irods_platform_string'] = get_irods_platform_string()
    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
