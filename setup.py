# -*- coding: utf-8 -*-
import re
import os

import setuptools


if __name__ == "__main__":
    MODULE_NAME = 'eppdperf'

    with open('README.md') as f:
        long_desc = f.read()


    setuptools.setup(
        name=MODULE_NAME,
        description='eppdperf: e-mail provider performance measurement scripts',
        setup_requires=['setuptools_scm'],
        use_scm_version = True,
        long_description=long_desc,
        long_description_content_type='text/x-rst',
        author='Nami, holger, merlinux',
        author_email='adbenitez@nauta.cu, holger@merlinux.eu',
        url='https://github.com/deltachat/eppdperf',
        package_dir={'': 'src'},
        packages = setuptools.find_packages('src'),
        classifiers=['Development Status :: 4 - Beta',
                     'Intended Audience :: Developers',
                     'License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)',
                     'Operating System :: POSIX',
                     'Operating System :: MacOS :: MacOS X',
                     'Topic :: Utilities',
                     'Programming Language :: Python :: 3'],
        entry_points='''
            [console_scripts]
            eppdperf=eppdperf.cmdline:main
        ''',
        python_requires='>=3.7',
        install_requires=['deltachat>=1.70'],
        include_package_data=True,
        zip_safe=False,
    )
