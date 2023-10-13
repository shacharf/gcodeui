# gcodeui
Simple ui to send gcode commands to a 3d printer / cnc

## Setup:
You need python 3.7 or later

```bash
pip install -r requirements
```

### Configuration
* Add / delete the list of "built-in" commands by updating the `config.yaml`` file. Below is an example:
```yaml
commands:
  - title: pos
    command: M114
    color: "#008000"
  - title: status
    command: M503
  - title: Init54
    command: 
    - G54
    - G92 X0 Y0
    - M211 S0
    - M117 CNC ready
  ```
## Run
```bash
python gcodeui.py
```

# Changelog
* 2023-10-14 - Created
