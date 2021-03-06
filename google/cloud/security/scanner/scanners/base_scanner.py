# Copyright 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Base scanner."""

import abc
import os
import shutil

from google.cloud.security.common.data_access import errors as db_errors
from google.cloud.security.common.data_access import violation_dao
from google.cloud.security.common.gcp_api import storage
from google.cloud.security.common.util import log_util


LOGGER = log_util.get_logger(__name__)


class BaseScanner(object):
    """This is a base class skeleton for scanners."""
    __metaclass__ = abc.ABCMeta

    OUTPUT_TIMESTAMP_FMT = '%Y%m%dT%H%M%SZ'
    SCANNER_OUTPUT_CSV_FMT = 'scanner_output_base.{}.csv'

    def __init__(self, global_configs, scanner_configs, snapshot_timestamp,
                 rules):
        """Constructor for the base pipeline.

        Args:
            global_configs (dict): Global configurations.
            scanner_configs (dict): Scanner configurations.
            snapshot_timestamp (str): Timestamp, formatted as YYYYMMDDTHHMMSSZ.
            rules (str): Fully-qualified path and filename of the rules file.
        """
        self.global_configs = global_configs
        self.scanner_configs = scanner_configs
        self.snapshot_timestamp = snapshot_timestamp
        self.rules = rules

    @abc.abstractmethod
    def run(self):
        """Runs the pipeline."""
        pass

    def _output_results_to_db(self, resource_name, violations):
        """Output scanner results to DB.

        Args:
            resource_name (str): Resource name.
            violations (list): A list of violations.

        Returns:
            list: Violations that encountered an error during insert.
        """
        resource_name = 'violations'
        (inserted_row_count, violation_errors) = (0, [])
        try:
            vdao = violation_dao.ViolationDao(self.global_configs)
            (inserted_row_count, violation_errors) = vdao.insert_violations(
                violations,
                resource_name=resource_name,
                snapshot_timestamp=self.snapshot_timestamp)
        except db_errors.MySQLError as err:
            LOGGER.error('Error importing violations to database: %s', err)

        # TODO: figure out what to do with the errors. For now, just log it.
        LOGGER.debug('Inserted %s rows with %s errors',
                     inserted_row_count, len(violation_errors))

        return violation_errors

    def _get_output_filename(self, now_utc):
        """Create the output filename.

        Args:
            now_utc (datetime): The datetime now in UTC. Generated at the top
                level to be consistent across the scan.

        Returns:
            str: The output filename for the csv, formatted with the
                now_utc timestamp.
        """
        output_timestamp = now_utc.strftime(self.OUTPUT_TIMESTAMP_FMT)
        output_filename = self.SCANNER_OUTPUT_CSV_FMT.format(output_timestamp)
        return output_filename

    def _upload_csv(self, output_path, now_utc, csv_name):
        """Upload CSV to Cloud Storage.

        Args:
            output_path (str): The output path for the csv.
            now_utc (datetime): The UTC timestamp of "now".
            csv_name (str): The csv_name.
        """
        output_filename = self._get_output_filename(now_utc)

        # If output path was specified, copy the csv temp file either to
        # a local file or upload it to Google Cloud Storage.
        full_output_path = os.path.join(output_path, output_filename)
        LOGGER.info('Output path: %s', full_output_path)

        if output_path.startswith('gs://'):
            # An output path for GCS must be the full
            # `gs://bucket-name/path/for/output`
            storage_client = storage.StorageClient()
            storage_client.put_text_file(
                csv_name, full_output_path)
        else:
            # Otherwise, just copy it to the output path.
            shutil.copy(csv_name, full_output_path)
