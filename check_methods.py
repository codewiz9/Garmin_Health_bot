import json
import inspect
from garminconnect import Garmin

methods = []
for name, member in inspect.getmembers(Garmin):
    if inspect.isfunction(member) and not name.startswith('_'):
        sig = str(inspect.signature(member))
        methods.append({"name": name, "signature": sig})

with open('garmin_all_methods.json', 'w') as f:
    json.dump(methods, f, indent=2)
