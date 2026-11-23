"""Sample logical CPU compute headroom; this is not a core reservation.

I/O wait is accounted separately from executing work. Its accounting is
approximate; reject decreasing counters, retain raw deltas and sibling samples,
and do not claim idle disks or exclusive physical cores.
"""
import os
from pathlib import Path
import time


def counters():
    rows = {}
    for line in Path('/proc/stat').read_text().splitlines():
        fields = line.split()
        if fields[0].startswith('cpu') and fields[0][3:].isdigit():
            rows[int(fields[0][3:])] = list(map(int, fields[1:9]))
    return rows


def measure_compute_headroom(allowed, interval_seconds=5, count=4, minimum=.8):
    allowed = set(allowed)
    times = []; samples = []
    for i in range(3):
        if i: time.sleep(interval_seconds)
        times.append(time.monotonic()); samples.append(counters())
    measurements = {}
    for cpu in samples[0].keys() & samples[1].keys() & samples[2].keys():
        deltas = [[b-a for a,b in zip(before[cpu],after[cpu])] for before,after in zip(samples,samples[1:])]
        valid = all(sum(d)>0 and all(v>=0 for v in d) for d in deltas)
        measurements[cpu] = {'deltas':deltas, 'valid':valid,
            'idle_fractions':[d[3]/sum(d) for d in deltas] if valid else [],
            'iowait_fractions':[d[4]/sum(d) for d in deltas] if valid else [],
            'nonexecuting_fractions':[(d[3]+d[4])/sum(d) for d in deltas] if valid else []}
    candidates = []
    for cpu in sorted(allowed & measurements.keys()):
        root=Path('/sys/devices/system/cpu')/('cpu'+str(cpu))/'topology'
        package,core=int((root/'physical_package_id').read_text()),int((root/'core_id').read_text())
        measured=measurements[cpu]
        if package<0 or core<0 or not measured['valid'] or min(measured['nonexecuting_fractions'])<minimum: continue
        candidates.append({'cpu':cpu,'package':package,'core':core,'siblings':(root/'thread_siblings_list').read_text().strip(),**measured})
    chosen=[];used=set()
    for row in sorted(candidates,key=lambda r:(-min(r['nonexecuting_fractions']),r['cpu'])):
        key=(row['package'],row['core'])
        if key in used: continue
        chosen.append(row);used.add(key)
        if len(chosen)==count:break
    return {'selected_cpus':[r['cpu'] for r in chosen] if len(chosen)==count else [],
        'selected_logical_cpus':chosen,'allowed_CPU_count':len(allowed),
        'sample_interval_seconds':[b-a for a,b in zip(times,times[1:])],
        'minimum_nonexecuting_fraction':minimum,'required_logical_CPUs':count,
        'physical_cores_exclusive':False,'load_average_diagnostic_only':os.getloadavg(),
        'all_logical_CPU_samples':measurements,'process_affinity_changed':False}


if __name__=='__main__':
    import json
    print(json.dumps(measure_compute_headroom(os.sched_getaffinity(0))))
