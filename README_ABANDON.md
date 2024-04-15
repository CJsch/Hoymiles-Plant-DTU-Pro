### Abandoned
Monitoring the coils frequently and setting them individually caused a bunch of weird behavior in the DTU unit I tested it on.
Certain functionality in the official hoymiles app stopped working. Luckily, reading all values from the modbus registers as implemented in this plugin
still works. The modbus endpoint to set all power limits also still works as expected.
If you would like to build upon this, feel free to but be aware that frequent coil reads (especially at night) seem to have significant
negative efects on the DTU unit


### Alternative solution
One NumberEntity that allows you to set the limit for all microinverters using the 0xC001 address.
I recommend only setting this value whenever all microinverters are currently producing at least some power.
This value is initialized as 100 instead of reading it from the DTU to prevent integration startup errors.
In order to use this, add the following to your `configuration.yaml`.

```yaml
number:
  - platform: hoymiles_dtu
    host: 192.168.2.5
    name: Hoymiles PV
    dtu_type: 0
    rw_coils:
      - "limit_active_power"
```

You will also need to override the code of the `custom_component` with the code in this fork.

### Example automation
The price of providing power to the net sometimes goes into the negative depending on the energy market.
Here's an example automation that I use to automatically set the production to 5%, which is close to our "average normal use".
```yaml
alias: Solar negative price
description: ""
trigger:
  - platform: numeric_state
    entity_id:
      - sensor.real_current_electricity_price_production
    for:
      hours: 0
      minutes: 5
      seconds: 0
    below: 0.001
condition:
  - condition: numeric_state
    entity_id: number.hoymiles_pv_inverters_power_limit_limit_active_power
    above: 10
  - condition: numeric_state
    entity_id: sensor.hoymiles_pv_pv_power
    above: 0.1
action:
  - service: number.set_value
    target:
      entity_id: number.hoymiles_pv_inverters_power_limit_limit_active_power
    data:
      value: "5"
  - service: notify.persistent_notification
    metadata: {}
    data:
      message: Solar limit to 5 percent due to negative price
mode: single
```