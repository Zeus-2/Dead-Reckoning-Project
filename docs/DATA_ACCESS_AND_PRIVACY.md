# Data access and privacy statement

## Purpose of the repository

I use this repository to preserve the implementation, experimental workflow and supporting research data for my MSc dissertation on vehicle telemetry, dead reckoning and driving-behaviour inference.

The repository associated with the dissertation is intended to remain **private and access-controlled**. I provide its link in the dissertation appendix so that authorised assessors can inspect the implementation and supporting evidence where required.

It is not intended to function as a public release of the complete research dataset.

## Why I restrict access

The project contains or may contain data that becomes privacy-sensitive when combined across time.

This includes:

- raw CAN and OBD telemetry;
- GPS latitude/longitude used as experimental ground truth;
- timestamps;
- vehicle speed, RPM, throttle and related operating signals;
- smartphone inertial and magnetometer measurements;
- journey start and end information;
- approximate locations associated with my home and workplace;
- reconstructed routes and intermediate outputs.

A core aim of the dissertation is to examine whether commodity vehicle telemetry can support route reconstruction and driving-behaviour inference. The research therefore demonstrates that apparently low-level telemetry can reveal more about a journey when multiple signals are combined.

For that reason, openly publishing the complete raw dataset would create an unnecessary privacy risk and would conflict with the data-minimisation approach used elsewhere in the project.

## Home and workplace locations

My local privacy configuration may contain approximate coordinates representing private locations such as my home and workplace. These coordinates are used only so that the preprocessing stage can remove a configured distance from the beginning or end of relevant recordings.

The distributable source-code configuration uses example coordinates instead.

I do not intend to place my real private-location configuration in a public repository.

## Raw vehicle telemetry

The raw logs are retained as part of the restricted academic evidence because they provide an audit trail from collection through cleaning, reconstruction and evaluation.

Raw CAN/OBD telemetry should not be interpreted as harmless simply because it does not always contain an explicit street address. When combined with timestamps, GPS ground truth, repeated journeys or inferred motion, it may reveal:

- where a journey began or ended;
- route characteristics;
- driving patterns;
- vehicle operating behaviour;
- repeated travel routines.

The restricted-access repository is therefore the appropriate place for the complete evidence set.

## Dissertation appendix access

The dissertation appendix may provide a link to the private GitHub repository. The purpose of that link is to allow authorised academic staff to review the source code, processing pipeline and supporting evidence.

Access to the repository does not imply permission for public redistribution of the underlying telemetry or private-location information.

## Public-release version

If I later create a public release, I should exclude or replace:

- raw CAN/OBD/GPS logs;
- real home/work coordinates;
- untrimmed journey files;
- files containing precise geographic ground truth;
- any generated output that could be used to recover private locations.

A public release should contain only:

- source code;
- example configuration;
- documentation;
- anonymised or sufficiently generalised derived results;
- selected dissertation figures that do not disclose private locations.

This separation allows the implementation to remain reproducible without unnecessarily exposing the sensitive research dataset.
