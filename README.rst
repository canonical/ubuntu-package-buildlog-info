============================
Ubuntu Package Buildlog Info
============================


.. image:: https://img.shields.io/pypi/v/ubuntu_package_buildlog_info.svg
        :target: https://pypi.python.org/pypi/ubuntu_package_buildlog_info

.. image:: https://img.shields.io/travis/philroche/ubuntu_package_buildlog_info.svg
        :target: https://travis-ci.com/philroche/ubuntu_package_buildlog_info

.. image:: https://readthedocs.org/projects/ubuntu-package-buildlog-info/badge/?version=latest
        :target: https://ubuntu-package-buildlog-info.readthedocs.io/en/latest/?version=latest
        :alt: Documentation Status




Tool to retrieve Ubuntu package buildlog info


* Free software: GNU General Public License v3
* Documentation: https://ubuntu-package-buildlog-info.readthedocs.io.

Example Usage
-------------

::

    ubuntu-package-buildlog-info --series jammy --package-version 3.0.4-2ubuntu2.2 --package-name apparmor


Features
--------

Downloads the buildlog, changes files and changelog for a package version in a series and extracts the buildinfo
from the buildlog file.

It also verifies that the buildinfo file is correct based on the checksum in the .changes file.

TODO
----

* Code cleanup now that we have a working version
* Write tests
* Add support for querying PPAs
* Add support for querying latest version of a package in a series if no version is specified
* Create snapcraft.yaml to build a snap package for easy distribution

Credits
-------

This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage
