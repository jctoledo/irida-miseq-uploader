#!/bin/bash

# This file is modified from https://irida.corefacility.ca/gitlab/irida/import-tool-for-galaxy/blob/development/irida_import/tests/integration/bash_scripts/install.sh

mkdir repos
pushd repos

echo "Downloading IRIDA..."
if ! git clone git@irida.corefacility.ca:irida/irida.git
then
    echo >&2 "Failed to clone"
else
  pushd irida
  git checkout master
  git fetch
  git reset --hard
  git clean -fd
  git pull
  echo "Preparing IRIDA for first excecution..."

  pushd lib
  ./install-libs.sh
  popd
  popd
  echo "IRIDA has been installed"
fi

