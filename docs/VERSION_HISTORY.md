# Reconstruction version progression

## V1 – baseline

My V1 implementation is intentionally simple. It uses OBD vehicle speed and a phone yaw estimate produced by projecting the rotation-rate vector onto gravity. One stationary gyroscope bias is used for the whole journey.

This gives me a clear baseline for accumulated heading drift.

## V2 – improved inertial reconstruction

My V2 no-map method keeps the same fundamental inputs but improves heading treatment by using:

- stable stationary windows;
- time-varying gyro-bias interpolation;
- zero-rate updates while stationary;
- adaptive deadbanding;
- a small median filter and exponential smoother;
- optional, quality-gated magnetometer heading-change fusion.

GPS is not used to construct the no-map route.

## V2 + OSM – map-assisted reconstruction

The map-assisted version uses the first post-privacy GPS point as a known start anchor. It does not use later GPS points or GPS bearing for inference.

Instead of simply snapping every point to the nearest road, I retain a small beam of plausible road hypotheses. Candidate transitions are scored using road distance, heading compatibility, OSM connectivity, road switching and weak speed/road-class plausibility.

This structure lets me compare a baseline, a more developed inertial method and an OSM-constrained method without hiding regressions when a more complicated method performs worse.
