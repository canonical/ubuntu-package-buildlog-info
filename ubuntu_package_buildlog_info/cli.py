#!/usr/bin/env python3

import faulthandler
import hashlib
import logging
import re
import sys

import click

import urllib.parse
from launchpadlib.launchpad import Launchpad
from launchpadlib.uris import service_roots

# Which archive pockets are checked
ARCHIVE_POCKETS = ["Release", "Security", "Updates", "Proposed"]
faulthandler.enable()


def _get_binary_packages(archive, version, binary_package_name, lp_arch_series, pocket, status="Published"):
    binaries = archive.getPublishedBinaries(
        exact_match=True,
        version=version,
        binary_name=binary_package_name,
        distro_arch_series=lp_arch_series,
        pocket=pocket,
        order_by_date=True,
        status=status,
    )
    return binaries


def _get_published_sources(archive, version, source_package_name, lp_series, pocket, status="Published"):
    sources = archive.getPublishedSources(
        exact_match=True,
        version=version,
        source_name=source_package_name,
        pocket=pocket,
        distro_series=lp_series,
        order_by_date=True,
        status=status,
    )
    return sources


def get_buildlog_info(package_series, package_name, package_version, package_architecture="amd64", ppas=[], lp_user=None):
    if lp_user:
        launchpad = Launchpad.login_with(
            lp_user,
            service_root=service_roots['production'], version='devel')
    else:
        # Log in to launchpad annonymously - we use launchpad to find
        # the package publish time
        launchpad = Launchpad.login_anonymously(
            'ubuntu-package-buildlog-info',
            service_root=service_roots['production'], version='devel')

    ubuntu = launchpad.distributions["ubuntu"]
    source_package_found = False
    for pocket in ARCHIVE_POCKETS:

        # TODO add support for PPAs
        # if args.ppa:
        #     ppa_owner, ppa_name = args.ppa.split('/')
        #     archive = launchpad.people[ppa_owner].getPPAByName(name=ppa_name)
        #     if args.pocket != 'Release':
        #         print('using pocket "Release" when using a PPA ...')
        #         pocket = 'Release'
        # else:
        archive = ubuntu.main_archive

        lp_series = ubuntu.getSeries(name_or_version=package_series)
        lp_arch_series = lp_series.getDistroArchSeries(archtag=package_architecture)

        for package_publication_status in ["Published", "Superseded"]:
            sources = _get_published_sources(archive,
                                             package_version,
                                             package_name,
                                             lp_series,
                                             pocket,
                                             status=package_publication_status)
            if len(sources) == 0:
                print(f'INFO: No {package_publication_status} sources found for {package_name} version {package_version} in {package_series} {pocket}')
                print('INFO: \tTrying to find a binary package with that name ...')
                # unable to find published sources for args.package.
                # Perhaps this is a binary package name so we can
                # do a lookup to see if there exists a source package for
                # args.package binary package.
                binaries = _get_binary_packages(archive,
                                                package_version,
                                                package_name,
                                                lp_arch_series,
                                                pocket,
                                                status=package_publication_status)
                if len(binaries):
                    # there were published binaries with this name.
                    # now get the source package name so we can get the changelog
                    for binary in binaries:
                        source_package_name = binary.source_package_name
                        sources = _get_published_sources(archive,
                                                         package_version,
                                                         source_package_name,
                                                         lp_series,
                                                         pocket,
                                                         status=package_publication_status)
                        if len(sources) > 0:
                            print(f'INFO: \tFound source package {source_package_name} for binary package '
                                  f'{package_name} version {package_version} with {package_publication_status} sources.')
                            source_package_found = True
                            break
                else:
                    print(f'INFO: \tNo {package_publication_status} binaries found for {package_name} version {package_version} in {package_series} {pocket}\n\n')
            else:
                print(f'INFO: \tFound source package '
                      f'{package_name} version {package_version} in {pocket} pocket with {package_publication_status} sources.')
                source_package_found = True
                break
        if source_package_found:
            break
    if len(sources) == 1:


        builds = sources[0].getBuilds()
        if len(builds) > 1:
            for build in builds:

                if build.arch_tag == package_architecture:
                    _build = builds[0]
                    source_package_name = _build.source_package_name
                    source_package_version = _build.source_package_version
                    source_package_arch_tag = _build.arch_tag

                    changelog_url = sources[0].changelogUrl()
                    url = launchpad._root_uri.append(urllib.parse.urlparse(changelog_url).path.lstrip('/'))
                    changelog_resp = launchpad._browser.get(url).decode('utf-8')
                    # write changelog_resp to file named {package_name}.changelog
                    with open(f'{source_package_name}_{source_package_version}_{source_package_arch_tag}.changelog', 'w') as f:
                        f.write(changelog_resp)

                    buildlog_url = _build.build_log_url
                    url = launchpad._root_uri.append(urllib.parse.urlparse(buildlog_url).path.lstrip('/'))
                    buildlog_resp = launchpad._browser.get(url).decode('utf-8')

                    # Find line with <<PKGBUILDDIR>> in buildlog_resp and set as pkg_builddir variable
                    pkg_builddir = ""
                    for buildlog_line in buildlog_resp.splitlines():
                        if "I: NOTICE: Log filtering will replace" in buildlog_line and "with '<<PKGBUILDDIR>>'" in buildlog_line:
                            # use regex to extract a directory path from the line eg 'build/apparmor-BXxSs1/apparmor-3.0.4'
                            pkg_builddir_regex = re.compile(r"'build/.*' ")
                            pkg_builddir = pkg_builddir_regex.search(buildlog_line).group(0).replace("'", "")
                            break

                    with open(f'{source_package_name}_{source_package_version}_{source_package_arch_tag}.buildlog', 'w') as f:
                        f.write(buildlog_resp)

                    buildinfo_start = "| Buildinfo                                                                    |"
                    buildinfo_end = "| Package contents                                                             |"
                    buildlog_header_separator = "+------------------------------------------------------------------------------+"
                    buildinfo = ""
                    append_to_buildinfo = False
                    for buildlog_line in buildlog_resp.splitlines():
                        if buildinfo_start in buildlog_line:
                            append_to_buildinfo = True

                        if buildinfo_end in buildlog_line:
                            break
                        if append_to_buildinfo and buildlog_line != buildinfo_start and buildlog_line != buildinfo_end and buildlog_line != buildlog_header_separator and buildlog_line != "":
                            buildinfo = "{}{}\n".format(buildinfo, buildlog_line)

                    # trim all whitepace from pkg_builddir
                    pkg_builddir = pkg_builddir.strip()
                    # replace <<PKGBUILDDIR>> in buildinfo with the actual path
                    buildinfo = buildinfo.replace("<<PKGBUILDDIR>>", pkg_builddir)

                    buildinfo_filename = f'{source_package_name}_{source_package_version}_{source_package_arch_tag}.buildinfo'
                    with open(buildinfo_filename, 'w') as f:
                        f.write(buildinfo)

                    changesfile_url = _build.changesfile_url
                    url = launchpad._root_uri.append(urllib.parse.urlparse(changesfile_url).path.lstrip('/'))
                    changesfile_resp = launchpad._browser.get(url).decode('utf-8')

                    # find the hashes of buildinfo_filename in the changesfile_resp and verify that they match hash
                    # of the buildinfo_filename file already written to disk
                    sha256_checksums_found = False
                    for changesfile_line in changesfile_resp.splitlines():
                        if "Checksums-Sha256:" in changesfile_line:
                            sha256_checksums_found = True
                        if sha256_checksums_found and buildinfo_filename in changesfile_line:
                            # get the hash from the changesfile_line
                            changesfile_buildinfo_hash = changesfile_line.split()[0]
                            # get the hash of the buildinfo_filename file
                            sha256hash = hashlib.sha256(buildinfo.encode('UTF-8')).hexdigest()

                            if changesfile_buildinfo_hash == sha256hash:
                                print(f'INFO: \tHash of {buildinfo_filename} matches hash in changes file.')
                            else:
                                print(f'INFO: \tHash of {buildinfo_filename} does not match hash in changes file.')
                            break

                    with open(f'{source_package_name}_{source_package_version}_{source_package_arch_tag}.changes', 'w') as f:
                        f.write(changesfile_resp)

        else:
            print(f'Unable to find builds for package {package_name} version {package_version}')
    else:
        print(f'Unable to find published package {package_name} version {package_version}')


@click.command()
@click.option(
    "--series",
    help="The Ubuntu series eg. '20.04' or 'focal'.",
    required=True,
)
@click.option(
    "--package-name",
    help="Package name",
    required=True,
)
@click.option(
    "--package-version",
    help="Package version",
    required=True,
)
@click.option(
    "--logging-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    required=False,
    default="ERROR",
    help="How detailed would you like the output.",
    show_default=True
)
@click.option(
    "--package-architecture",
    help="The architecture to use when querying package "
    "version in the archive. We use this in our Launchpad "
    'query to query either "source" package or "amd64" package '
    'version. Using "amd64" will query the version of the '
    'binary package. "source" is a valid value for '
    "architecture with Launchpad and will query the version of "
    "the source package. The default is amd64. ",
    required=True,
    default="amd64",
    show_default=True
)
@click.option(
    "--ppa",
    "ppas",
    required=False,
    multiple=True,
    type=click.STRING,
    help="Additional PPAs that you wish to query for package version status."
    "Expected format is "
    "ppa:'%LAUNCHPAD_USERNAME%/%PPA_NAME%' eg. ppa:philroche/cloud-init"
    "Multiple --ppa options can be specified",
    default=[]
)
@click.option(
    "--launchpad-user",
    "lp_user",
    required=False,
    type=click.STRING,
    help="Launchpad username to use when querying PPAs. This is important id "
         "you are querying PPAs that are not public.",
    default=None
)
@click.pass_context
def ubuntu_package_buildlog_info(
    ctx, series, package_name, package_version, logging_level, package_architecture, ppas, lp_user
):
    # type: (Dict, Text, Text,Text, Text, Optional[Text], Text) -> None
    """
    Watch specified packages in the ubuntu archive for transition between
    archive pockets/PPAs. Useful when waiting for a package update to be published.
    """

    # We log to stderr so that a shell calling this will not have logging
    # output in the $() capture.
    level = logging.getLevelName(logging_level)
    logging.basicConfig(
        level=level, stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s"
    )

    get_buildlog_info(series, package_name, package_version, package_architecture, list(ppas), lp_user)


if __name__ == "__main__":
    ubuntu_package_buildlog_info(obj={})
