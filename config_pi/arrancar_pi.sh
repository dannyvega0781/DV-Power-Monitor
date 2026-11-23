#!/bin/bash
set -e

cd /home/dvmonitor/DV_Power_Monitor_Actual

source /home/dvmonitor/.config/dv-power-monitor/entorno.sh

exec /home/dvmonitor/DV_Power_Monitor_Actual/.venv/bin/python -u iniciar_app.py
