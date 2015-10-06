#!/usr/bin/python

import abc
import json
import os
import tempfile
import time


class UnimplementedStrategy(object):
    def __init__(self, module):
        self.module = module
        self.unimplmented_error()

    def install(self):
        self.unimplmented_error()

    def unimplemented_error(self):
        platform = get_platform()
        distribution = get_distribution()
        if distribution is not None:
            msg_platform = '{0} ({1})'.format(platform, distribution)
        else:
            msg_platform = platform
        self.module.fail_json(msg='irods_installation_icat_server module cannot be used on platform {0}'.format(msg_platform))

class IcatInstaller(object):
    platform = 'Generic'
    distribution = None
    strategy_class = UnimplementedStrategy
    def __new__(cls, *args, **kwargs):
        return load_platform_subclass(IcatInstaller, args, kwargs)

    def __init__(self, module):
        self.strategy = self.strategy_class(module)

    def install(self):
        return self.strategy.install()

class GenericStrategy(object):
    __metaclass__ = abc.ABCMeta
    def __init__(self, module):
        self.module = module
        self.irods_packages_root_directory = module.params['irods_packages_root_directory']
        self.icat_database_type = module.params['icat_database_type']
        self.icat_database_hostname = module.params['icat_database_hostname']

    @abc.abstractmethod
    def install_database(self):
        pass

    def install(self):
        self.install_icat()
        self.install_database_plugin()
        self.install_database()
        self.configure_database()
        self.run_setup_script()
        self.post_install_configuration()
        self.install_testing_dependencies()

    def install_testing_dependencies(self):
        if self.testing_dependencies:
            install_os_packages(self.testing_dependencies)
        self.module.run_command('wget https://bootstrap.pypa.io/get-pip.py', check_rc=True)
        self.module.run_command('sudo -E python get-pip.py', check_rc=True)
        self.module.run_command('sudo -E pip2 install --upgrade unittest-xml-reporting', check_rc=True)

    @property
    def testing_dependencies(self):
        return ['bonnie++', 'fuse', 'git']

    def install_icat(self):
        icat_package_basename = filter(lambda x:'irods-icat' in x, os.listdir(self.irods_packages_directory))[0]
        icat_package = os.path.join(self.irods_packages_directory, icat_package_basename)
        install_os_packages_from_files([icat_package])

    @property
    def irods_packages_directory(self):
        return os.path.join(self.irods_packages_root_directory, get_irods_platform_string())

    def install_database_plugin(self):
        database_plugin_basename = filter(lambda x:'irods-database-plugin-'+self.icat_database_type+'-' in x, os.listdir(self.irods_packages_directory))[0]
        database_plugin = os.path.join(self.irods_packages_directory, database_plugin_basename)
        install_os_packages_from_files([database_plugin])

    def configure_database(self):
        if self.icat_database_type == 'postgres':
            self.module.run_command(['sudo', 'su', '-', 'postgres', '-c', 'createuser -s irods'], check_rc=True)
            self.module.run_command(['sudo', 'su', '-', 'postgres', '-c', '''psql -c "alter role irods with password 'testpassword'"'''], check_rc=True)
            self.module.run_command(['sudo', 'su', '-', 'postgres', '-c', "createdb 'ICAT'"], check_rc=True)
        elif self.icat_database_type == 'mysql':
            self.module.run_command(['mysql', '--user=root', '--password=password', '-e', "grant all on ICAT.* to 'irods'@'localhost' identified by 'testpassword'"], check_rc=True)
            self.module.run_command(['mysql', '--user=root', '--password=password', '-e', 'flush privileges'], check_rc=True)
            self.module.run_command(['mysql', '--user=root', '--password=password', '-e', 'drop database if exists ICAT;'], check_rc=True)
            self.module.run_command(['mysql', '--user=root', '--password=password', '-e', 'create database ICAT character set latin1 collate latin1_general_cs;'], check_rc=True)
        elif self.icat_database_type == 'oracle':
            pass
        else:
            assert False, self.icat_database_type

    def run_setup_script(self):
        setup_script_location_dict = {
            'postgres': '/var/lib/irods/tests/localhost_setup_postgres.input',
            'mysql': '/var/lib/irods/tests/localhost_setup_mysql.input',
            'oracle': '/var/lib/irods/tests/remote_setup_oracle.input',
        }
        setup_script = setup_script_location_dict[self.icat_database_type]
        output_log = '/var/lib/irods/iRODS/installLogs/setup_irods.output'
        self.module.run_command(['sudo', 'su', '-c', '/var/lib/irods/packaging/setup_irods.sh < {0} > {1} 2>&1'.format(setup_script, output_log)], use_unsafe_shell=True, check_rc=True)

    def post_install_configuration(self):
        pass

    def install_mysql_pcre(self, dependencies, mysql_service):
        install_os_packages(dependencies)
        local_pcre_git_dir = os.path.expanduser('~/lib_mysqludf_preg')
        self.module.run_command(['git', 'clone', 'https://github.com/mysqludf/lib_mysqludf_preg.git', local_pcre_git_dir], check_rc=True)
        self.module.run_command(['git', 'checkout', 'lib_mysqludf_preg-1.1'], cwd=local_pcre_git_dir, check_rc=True)
        self.module.run_command(['autoreconf', '--force', '--install'], cwd=local_pcre_git_dir, check_rc=True)
        self.module.run_command(['sudo', './configure'], cwd=local_pcre_git_dir, check_rc=True)
        self.module.run_command(['sudo', 'make', 'install'], cwd=local_pcre_git_dir, check_rc=True)
        self.module.run_command('mysql --user=root --password="password" < installdb.sql', use_unsafe_shell=True, cwd=local_pcre_git_dir, check_rc=True)
        self.module.run_command(['sudo', 'service', mysql_service, 'restart'], check_rc=True)

class RedHatStrategy(GenericStrategy):
    @property
    def testing_dependencies(self):
        return super(RedHatStrategy, self).testing_dependencies + ['python-unittest2']

    def install_database_plugin(self):
        if self.icat_database_type != 'oracle':
            return super(RedHatStrategy, self).install_database_plugin()
        self.install_oracle_dependencies()
        self.install_oracle_plugin()

    def install_oracle_dependencies(self):
        tar_file = os.path.expanduser('~/oci.tar')
        self.module.run_command(['wget', 'http://people.renci.org/~jasonc/irods/oci.tar', '-O', tar_file], check_rc=True)
        tar_dir = os.path.expanduser('~/oci')
        os.mkdir(tar_dir)
        self.module.run_command(['tar', '-xf', 'oci.tar', '-C', tar_dir], check_rc=True)
        self.module.run_command('sudo rpm -i --nodeps ./oci/*', use_unsafe_shell=True, check_rc=True)

    def install_oracle_plugin(self):
        database_plugin_basename = filter(lambda x:'irods-database-plugin-'+self.icat_database_type+'-' in x, os.listdir(self.irods_packages_directory))[0]
        database_plugin = os.path.join(self.irods_packages_directory, database_plugin_basename)
        self.module.run_command(['sudo', 'rpm', '-i', '--nodeps', database_plugin], check_rc=True)

    def install_database(self):
        if self.icat_database_type == 'postgres':
            install_os_packages(['postgresql-server'])
            self.module.run_command('sudo su - postgres -c "initdb"', check_rc=True)
            self.module.run_command('sudo su - postgres -c "pg_ctl -D /var/lib/pgsql/data -l logfile start"', check_rc=True)
            time.sleep(5)
        elif self.icat_database_type == 'mysql':
            if get_distribution_version_major() == '6':
                install_os_packages(['mysql-server'])
                self.module.run_command(['sudo', 'service', 'mysqld', 'start'], check_rc=True)
                self.module.run_command(['mysqladmin', '-u', 'root', 'password', 'password'], check_rc=True)
                self.module.run_command(['sudo', 'sed', '-i', r's/\[mysqld\]/\[mysqld\]\nlog_bin_trust_function_creators=1/', '/etc/my.cnf'], check_rc=True)
                self.module.run_command(['sudo', 'service', 'mysqld', 'restart'], check_rc=True)
                self.install_mysql_pcre(['pcre-devel', 'gcc', 'make', 'automake', 'mysql-devel', 'autoconf', 'git'], 'mysqld')
            elif get_distribution_version_major() == '7':
                install_os_packages(['mariadb-server'])
                self.module.run_command(['sudo', 'systemctl', 'start', 'mariadb'], check_rc=True)
                self.module.run_command(['mysqladmin', '-u', 'root', 'password', 'password'], check_rc=True)
                self.module.run_command(['sudo', 'sed', '-i', r's/\[mysqld\]/\[mysqld\]\nlog_bin_trust_function_creators=1/', '/etc/my.cnf'], check_rc=True)
                self.module.run_command(['sudo', 'systemctl', 'restart', 'mariadb'], check_rc=True)
                self.install_mysql_pcre(['pcre-devel', 'gcc', 'make', 'automake', 'mysql-devel', 'autoconf', 'git'], 'mariadb')
            else:
                assert False, get_distribution_version_major()
        elif self.icat_database_type == 'oracle':
            with tempfile.NamedTemporaryFile() as f:
                f.write('''
export LD_LIBRARY_PATH=/usr/lib/oracle/11.2/client64/lib:$LD_LIBRARY_PATH
export ORACLE_HOME=/usr/lib/oracle/11.2/client64
export PATH=$ORACLE_HOME/bin:$PATH
''')
                f.flush()
                self.module.run_command(['sudo', 'su', '-c', "cat '{0}' >> /etc/profile.d/oracle.sh".format(f.name)], check_rc=True)
            self.module.run_command(['sudo', 'su', '-c', "echo 'ORACLE_HOME=/usr/lib/oracle/11.2/client64' >> /etc/environment"], check_rc=True)
            self.module.run_command('sudo mkdir -p /usr/lib/oracle/11.2/client64/network/admin', check_rc=True)
            tns_contents = '''
ICAT =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = default-cloud-hostname-oracle.example.org)(PORT = 1521))
    (CONNECT_DATA =
      (SERVER = DEDICATED)
      (SERVICE_NAME = ICAT.example.org)
    )
  )
'''
            self.module.run_command(['sudo', 'su', '-c', "echo '{0}' > /usr/lib/oracle/11.2/client64/network/admin/tnsnames.ora".format(tns_contents)], check_rc=True)
        else:
            assert False, self.icat_database_type

    def post_install_configuration(self):
        self.enable_pam()

    def enable_pam(self):
        subprocess.check_call('''sudo sh -c "echo 'auth        sufficient    pam_unix.so' > /etc/pam.d/irods"''', shell=True)

    def install_testing_dependencies(self):
        super(RedHatStrategy, self).install_testing_dependencies()
        if get_distribution_version_major() == '6':
            self.module.run_command(['sudo', 'usermod', '-a', '-G', 'fuse', 'irods'], check_rc=True)

class DebianStrategy(GenericStrategy):
    def install_database(self):
        if self.icat_database_type == 'postgres':
            install_os_packages(['postgresql'])
        elif self.icat_database_type == 'mysql':
            self.module.run_command(['sudo', 'debconf-set-selections'], data='mysql-server mysql-server/root_password password password', check_rc=True)
            self.module.run_command(['sudo', 'debconf-set-selections'], data='mysql-server mysql-server/root_password_again password password', check_rc=True)
            install_os_packages(['mysql-server'])
            self.module.run_command(['sudo', 'su', '-', 'root', '-c', "echo '[mysqld]' > /etc/mysql/conf.d/irods.cnf"], check_rc=True)
            self.module.run_command(['sudo', 'su', '-', 'root', '-c', "echo 'log_bin_trust_function_creators=1' >> /etc/mysql/conf.d/irods.cnf"], check_rc=True)
            self.module.run_command(['sudo', 'service', 'mysql', 'restart'], check_rc=True)
            self.install_mysql_pcre(['libpcre3-dev', 'libmysqlclient-dev', 'build-essential', 'libtool', 'autoconf', 'git'], 'mysql')
        else:
            assert False, self.icat_database_type

class SuseStrategy(GenericStrategy):
    def install_database(self):
        if self.icat_database_type == 'postgres':
            install_os_packages(['postgresql-server'])
            self.module.run_command('sudo su - postgres -c "initdb"', check_rc=True)
            conf_cmd = '''sudo su - postgres -c "echo 'standard_conforming_strings = off' >> /var/lib/pgsql/data/postgresql.conf"'''
            self.module.run_command(conf_cmd, check_rc=True)
            self.module.run_command('sudo su - postgres -c "pg_ctl -D /var/lib/pgsql/data -l logfile start"', check_rc=True)
            time.sleep(5)
        elif self.icat_database_type == 'mysql':
            install_os_packages(['mysql-community-server'])
            self.module.run_command(['sudo', 'su', '-', 'root', '-c', "echo '[mysqld]' > /etc/my.cnf.d/irods.cnf"], check_rc=True)
            self.module.run_command(['sudo', 'su', '-', 'root', '-c', "echo 'log_bin_trust_function_creators=1' >> /etc/my.cnf.d/irods.cnf"], check_rc=True)
            self.module.run_command(['sudo', 'service', 'mysql', 'restart'], check_rc=True)
            self.module.run_command(['mysqladmin', '-u', 'root', 'password', 'password'], check_rc=True)
            self.module.run_command(['sudo', 'service', 'mysql', 'restart'], check_rc=True)
            self.install_mysql_pcre(['libmysqlclient-devel', 'autoconf', 'git'], 'mysql')
        else:
            assert False, self.icat_database_type

    def post_install_configuration(self):
        self.enable_pam()

    def enable_pam(self):
        subprocess.check_call('''sudo sh -c "echo 'auth        sufficient    pam_unix.so' > /etc/pam.d/irods"''', shell=True)

class CentOS6IcatInstaller(IcatInstaller):
    platform = 'Linux'
    distribution = 'Centos'
    strategy_class = RedHatStrategy

class CentOS7IcatInstaller(IcatInstaller):
    platform = 'Linux'
    distribution = 'Centos linux'
    strategy_class = RedHatStrategy

class UbuntuIcatInstaller(IcatInstaller):
    platform = 'Linux'
    distribution = 'Ubuntu'
    strategy_class = DebianStrategy

class OpenSUSEInstaller(IcatInstaller):
    platform = 'Linux'
    distribution = 'Opensuse '
    strategy_class = SuseStrategy

def main():
    module = AnsibleModule(
        argument_spec = dict(
            irods_packages_root_directory=dict(type='str', required=True),
            icat_database_type=dict(choices=['postgres', 'mysql', 'oracle'], type='str', required=True),
            icat_database_hostname=dict(type='str', required=True),
        ),
        supports_check_mode=False,
    )

    installer = IcatInstaller(module)
    installer.install()

    result = {}
    result['changed'] = True
    result['complex_args'] = module.params

    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
