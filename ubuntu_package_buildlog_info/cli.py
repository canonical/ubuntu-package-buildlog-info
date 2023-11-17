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


def get_buildlog_info(
    package_series, package_name, package_version, package_architecture="amd64", ppas=[], lp_user=None
):
    """
    Get buildlog info for a package in the Ubuntu archive.

    Ubuntu package builds currently do not publish a buildinfo file. However, the buildlog file contains
    the contents buildinfo file. This script downloads the buildlog file, extracts the buildinfo file and verifies
    that the buildinfo file is correct based on the checksum in the .changes file.

    Downloads the buildlog, changes files and changelog for a package version in a series and extracts
    the buildinfofile from the buildlog file.

    It also verifies that the buildinfo file is correct based on the checksum in the .changes file.

    * First we query the Ubuntu archive for the source package version in the specified series and pocket.
    * If the source package version is not found we query the archive for the binary package version in
      the specified series and pocket.
    * If the binary package version is found we get the source package name from the binary package and
        query the archive for the source package version in the specified series and pocket.
    * If the source package version is found we download the buildlog, changes file and changelog for the
        source package version in the specified series and pocket.
    * We then extract the buildinfo file from the buildlog file.
    * We then verify that the buildinfo file is correct based on the checksum in the .changes file.
    """
    if lp_user:
        launchpad = Launchpad.login_with(lp_user, service_root=service_roots["production"], version="devel")
    else:
        # Log in to launchpad annonymously - we use launchpad to find
        # the package publish time
        launchpad = Launchpad.login_anonymously(
            "ubuntu-package-buildlog-info", service_root=service_roots["production"], version="devel"
        )

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
            sources = _get_published_sources(
                archive, package_version, package_name, lp_series, pocket, status=package_publication_status
            )
            if len(sources) == 0:
                print(
                    f"INFO: No {package_publication_status} sources found for {package_name} version {package_version} in {package_series} {pocket}"
                )
                print("INFO: \tTrying to find a binary package with that name ...")
                # unable to find published sources for source package package_name.
                # Perhaps this is a binary package name so we can
                # do a lookup to see if there exists a source package for
                # package_name binary package.
                binaries = _get_binary_packages(
                    archive, package_version, package_name, lp_arch_series, pocket, status=package_publication_status
                )
                if len(binaries):
                    # there were published binaries with this name.
                    # now get the source package name so we can get the changelog
                    for binary in binaries:
                        source_package_name = binary.source_package_name
                        sources = _get_published_sources(
                            archive,
                            package_version,
                            source_package_name,
                            lp_series,
                            pocket,
                            status=package_publication_status,
                        )
                        if len(sources) > 0:
                            print(
                                f"INFO: \tFound source package {source_package_name} for binary package "
                                f"{package_name} version {package_version} with {package_publication_status} sources."
                            )
                            source_package_found = True
                            break
                else:
                    print(
                        f"INFO: \tNo {package_publication_status} binaries found for {package_name} version {package_version} in {package_series} {pocket}\n\n"
                    )
            else:
                print(
                    f"INFO: \tFound source package "
                    f"{package_name} version {package_version} in {pocket} pocket with {package_publication_status} sources."
                )
                source_package_found = True
                # we have found the source package, so we can stop iterating over the publication statuses
                break
        if source_package_found:
            # if we have found the source package we can stop iterating over the pockets
            break

    # We now have a source package we can start querying for the buildlog, changes file and changelog
    if len(sources) == 1:
        builds = sources[0].getBuilds()
        if len(builds) > 1:
            # we need to find the build for the correct architecture
            architecture_build_found = False
            for build in builds:
                if build.arch_tag == package_architecture:
                    architecture_build_found = True
                    source_package_name = build.source_package_name
                    source_package_version = build.source_package_version
                    source_package_arch_tag = build.arch_tag

                    # Download the changelog file for this build
                    changelog_url = sources[0].changelogUrl()
                    url = launchpad._root_uri.append(urllib.parse.urlparse(changelog_url).path.lstrip("/"))
                    changelog_resp = launchpad._browser.get(url).decode("utf-8")
                    # write changelog_resp to file named
                    # {source_package_name}_{source_package_version}_{source_package_arch_tag}.changelog
                    with open(
                        f"{source_package_name}_{source_package_version}_{source_package_arch_tag}.changelog", "w"
                    ) as f:
                        f.write(changelog_resp)
                        print(
                            f"INFO: \tchangelog file writen to "
                            f"{source_package_name}_{source_package_version}_{source_package_arch_tag}.changelog"
                        )

                    # Download the build log for this build
                    buildlog_url = build.build_log_url
                    url = launchpad._root_uri.append(urllib.parse.urlparse(buildlog_url).path.lstrip("/"))
                    buildlog_resp = launchpad._browser.get(url).decode("utf-8")

                    # The build log contains <<PKGBUILDDIR>> which is a placeholder for the actual path to the
                    # build directory. We need to replace <<PKGBUILDDIR>> with the actual path to the build
                    # directory so that we can extract an accurate buildinfo file from the buildlog file.
                    # Find line with <<PKGBUILDDIR>> in buildlog_resp and set as pkg_builddir variable
                    pkg_builddir = ""
                    for buildlog_line in buildlog_resp.splitlines():
                        if (
                            "I: NOTICE: Log filtering will replace" in buildlog_line
                            and "with '<<PKGBUILDDIR>>'" in buildlog_line
                        ):
                            # use regex to extract a directory path from the line eg 'build/apparmor-BXxSs1/apparmor-3.0.4'
                            pkg_builddir_regex = re.compile(r"'build/.*' ")
                            pkg_builddir = pkg_builddir_regex.search(buildlog_line).group(0).replace("'", "")
                            # trim all whitepace from pkg_builddir
                            pkg_builddir = pkg_builddir.strip()
                            # we have found the line with <<PKGBUILDDIR>> so we can stop iterating over the lines
                            # in the buildlog
                            break

                    # write the build log to file named
                    # {source_package_name}_{source_package_version}_{source_package_arch_tag}.buildlog
                    with open(
                        f"{source_package_name}_{source_package_version}_{source_package_arch_tag}.buildlog", "w"
                    ) as f:
                        f.write(buildlog_resp)
                        print(
                            f"INFO: \tbuildlog writen to "
                            f"{source_package_name}_{source_package_version}_{source_package_arch_tag}.buildlog"
                        )

                    # The buildinfo file is contained between the lines
                    # | Buildinfo                                                                    |
                    # and
                    # | Package contents                                                             |
                    # in the build log.
                    buildinfo_start = "| Buildinfo                                                                    |"
                    buildinfo_end = "| Package contents                                                             |"
                    buildlog_header_separator = (
                        "+------------------------------------------------------------------------------+"
                    )
                    buildinfo = ""
                    append_to_buildinfo = False
                    for buildlog_line in buildlog_resp.splitlines():
                        if buildinfo_start in buildlog_line:
                            append_to_buildinfo = True

                        if buildinfo_end in buildlog_line:
                            # we have reached the end of the buildinfo section so we can stop iterating over the lines
                            break
                        if (
                            append_to_buildinfo
                            and buildlog_line != buildinfo_start
                            and buildlog_line != buildinfo_end
                            and buildlog_line != buildlog_header_separator
                            and buildlog_line != ""
                        ):
                            buildinfo = "{}{}\n".format(buildinfo, buildlog_line)

                    # replace <<PKGBUILDDIR>> in buildinfo with the actual path
                    buildinfo = buildinfo.replace("<<PKGBUILDDIR>>", pkg_builddir)

                    buildinfo_filename = (
                        f"{source_package_name}_{source_package_version}_{source_package_arch_tag}.buildinfo"
                    )
                    with open(buildinfo_filename, "w") as f:
                        f.write(buildinfo)
                        print(
                            f"INFO: \tbuildinfo file writen to "
                            f"{source_package_name}_{source_package_version}_{source_package_arch_tag}.buildinfo"
                        )

                    changesfile_url = build.changesfile_url
                    url = launchpad._root_uri.append(urllib.parse.urlparse(changesfile_url).path.lstrip("/"))
                    changesfile_resp = launchpad._browser.get(url).decode("utf-8")

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
                            sha256hash = hashlib.sha256(buildinfo.encode("UTF-8")).hexdigest()

                            if changesfile_buildinfo_hash == sha256hash:
                                print(f"INFO: \tHash of {buildinfo_filename} matches hash in changes file.")
                            else:
                                print(f"INFO: \tHash of {buildinfo_filename} does not match hash in changes file.")
                            # we have found the hash of the buildinfo_filename in the changes file so we can stop
                            # iterating over the changesfile lines
                            break

                    # write changesfile_resp to file named
                    # {source_package_name}_{source_package_version}_{source_package_arch_tag}.changes
                    with open(
                        f"{source_package_name}_{source_package_version}_{source_package_arch_tag}.changes", "w"
                    ) as f:
                        f.write(changesfile_resp)
                        print(
                            f"INFO: \tchanges file writen to {source_package_name}_{source_package_version}_{source_package_arch_tag}.changes"
                        )

                if architecture_build_found:
                    # if we have found the build for the correct architecture we can stop iterating over the builds
                    break
        else:
            print(f"Unable to find builds for package {package_name} version {package_version}")
    else:
        print(f"Unable to find published package {package_name} version {package_version}")


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
    show_default=True,
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
    show_default=True,
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
    default=[],
)
@click.option(
    "--launchpad-user",
    "lp_user",
    required=False,
    type=click.STRING,
    help="Launchpad username to use when querying PPAs. This is important id "
    "you are querying PPAs that are not public.",
    default=None,
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
    logging.basicConfig(level=level, stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s")

    get_buildlog_info(series, package_name, package_version, package_architecture, list(ppas), lp_user)


if __name__ == "__main__":
    ubuntu_package_buildlog_info(obj={})
