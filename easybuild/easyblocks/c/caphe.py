##
# Copyright 2009-2012 Stijn De Weirdt
# Copyright 2010 Dries Verdegem
# Copyright 2010-2012 Kenneth Hoste
# Copyright 2011 Pieter De Baets
# Copyright 2011-2012 Jens Timmerman
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
#
# http://github.com/hpcugent/easybuild
#
# EasyBuild is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# EasyBuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
##
"""
EasyBuild support for CAPHE, implemented as an easyblock
"""
import fileinput
import os
import shutil
import re
import sys
from distutils.version import LooseVersion

from easybuild.easyblocks.cmakepythonpackage import EB_CMakePythonPackage
from easybuild.tools.filetools import mkdir, run_cmd
from easybuild.tools.modules import get_software_root, get_software_version


class EB_CAPHE(EB_CMakePythonPackage):
    """
    Support for building CAPHE
    """

    def configure(self):

        # make sure that required dependencies are loaded
        deps = ['Boost', 'CMake', 'Python', 'SWIG']
        depsdict = {}
        for dep in deps:
            deproot = get_software_root(dep)
            if not deproot:
                self.log.error("Dependency %s not available." % dep)
            else:
                depsdict.update({dep: deproot})
                depsdict.update({"%s_version" % dep: get_software_version(dep)})

        # adjust config files where needed
        blas_libs = "-L%s %s" % (os.getenv('BLAS_LIB_DIR'), os.getenv('LIBBLAS_MT'))
        lapack_libs = "-L%s %s" % (os.getenv('LAPACK_LIB_DIR'), os.getenv('LIBLAPACK_MT'))

        numpyincludepath = os.path.join(self.pylibdir, 'numpy', 'core', 'include')

        # several files need to be patches to correct hardcoded settings
        ufconfigvars = {
                        'CC\s*=\s*': os.getenv('CC'),
                        'CFLAGS\s*=\s*': os.getenv('CFLAGS'),
                        'CPLUSPLUS\s*=\s*': os.getenv('CXX'),
                        'F77\s*=\s*': os.getenv('F77'),
                        'BLAS\s*=\s*': blas_libs,
                        'LAPACK\s*=\s*': lapack_libs
                       }

        metisvars = {
                     'CC\s*=\s*': os.getenv('CC'),
                     'OPTFLAGS\s*=\s*': os.getenv('CFLAGS')
                     }

        pythonvars = {
                      '\s+SET\(CMAKE_CXX_FLAGS\s+"\${CMAKE_CXX_FLAGS}\s+-I': '%s")' % numpyincludepath
                      }

        cmakevars = {
                     '\s+set\s*\(CMAKE_SHARED_LINKER_FLAGS\s+"\${CMAKE_SHARED_LINKER_FLAGS}\s+':' %s")' % lapack_libs,
                     '\s+SET\(CMAKE_INSTALL_PREFIX\s+': '%s)' % self.installdir
                     }

        filestopatch = {
                        os.path.join('contrib', 'UFconfig', 'UFconfig.mk'): ufconfigvars,
                        os.path.join('contrib', 'metis-4.0.3', 'Makefile.in'): metisvars,
                        os.path.join('python', 'CMakeLists.txt'): pythonvars,
                        'CMakeLists.txt': cmakevars,
                        }

        for (f, vardict) in filestopatch.items():
            self.log.debug("Patching file %s: %s" % (f, vardict))
            try:
                for line in fileinput.input(f, inplace=1, backup='.pre.patch.by.easybuild'):
                    for (var, val) in vardict.items():
                        regexp = re.compile("^(%s).*$" % var, re.M)
                        res = regexp.search(line)
                        # ensure a single match, or else fail
                        if res and len(res.groups()) == 1:
                            m = res.groups()[0]
                            line = regexp.sub("%s%s" % (m, val), line)
                            vardict.pop(var)  # remove if substitution was performed
                    sys.stdout.write(line)
                # check if all substitutions were performed
                if vardict:
                    self.log.error("Substition in %s failed for: %s" % (f, vardict.keys()))

            except IOError, err:
                self.log.error("Problem occured when trying to configure options for %s: %s" % (f, err))

        # update CMake configure options
        self.updatecfg('configopts', '-DBOOST_INCLUDE_DIR=%s' % os.path.join(depsdict['Boost'], 'include'))
        self.updatecfg('configopts', '-DSWIG_DIR=%s' % depsdict['SWIG'])
        pythonver = '.'.join(depsdict['Python_version'].split('.')[0:2])
        python_inc = os.path.join(depsdict['Python'], 'include', 'python%s' % pythonver)
        python_lib = os.path.join(depsdict['Python'], 'lib', 'libpython%s.so' % pythonver)
        self.updatecfg('configopts', '-DPYTHON_INCLUDE_DIR=%s -DPYTHON_LIBRARY=%s' % (python_inc, python_lib))
        if get_software_root('imkl'):
            self.updatecfg('configopts', '-DINTEL_MKL_ROOT_DIR=%s -DMKL_OPTION=ON' % depsdict['imkl'])

        EB_CMakePythonPackage.configure(self)

    def make(self):

        cwd = os.getcwd()
        os.chdir('contrib')

        os.chmod("make_klu.sh", 0755)
        cmd = "./make_klu.sh"

        run_cmd(cmd, log_all=True, simple=True)

        os.chdir(cwd)

        cmd = "make"
        run_cmd(cmd, log_all=True, simple=True)

    def make_install(self):

        if LooseVersion(self.version()) >= LooseVersion("1.4"):

            EB_CMakePythonPackage.make_install(self)

        else:
            # old versions do not support the setup.py approach yet

            caphedir = "%s-%s" % (self.name().lower(), self.version())

            pylibinstalldir = os.path.join(self.installdir, self.pylibdir)
            mkdir(pylibinstalldir, parents=True)

            for f in [os.path.join("python", "_caphe.so"),
                      os.path.join("python", "caphe.py"),
                      os.path.join("src", "libodeproblemnetwork.so"),
                      os.path.join("contrib", "liballklu.so")]:

                try:
                    shutil.copy2(os.path.join(self.builddir, caphedir, f),
                                 pylibinstalldir)
                except OSError, err:
                    self.log.error("Failed to copy file %s to install directory: %s" % (f, err))

            try:
                ctdir = 'caphetools'
                shutil.copytree(os.path.join(self.builddir, caphedir, ctdir),
                                os.path.join(self.installdir, ctdir))
            except OSError, err:
                self.log.error("Failed to copy caphetools dir to install directory: %s" % err)

#    def make_module_extra(self):
##        """Also set LD_LIBRARY_PATH."""
#
#        txt = EB_CMakePythonPackage.make_module_extra(self)

#        txt += """prepend-path\tLD_LIBRARY_PATH\t\t$root\n"""
#
#return txt
