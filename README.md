# DV Power Monitor

Sistema de monitoreo de consumo eléctrico DC desarrollado por Daniel Vega Rivera para el proyecto Capstone ELEN 4810.

Un Arduino Mega 2560 lee un INA219 y comunica las mediciones por USB a una Raspberry Pi 4 o a una laptop Windows. Python y Flask presentan el dashboard en la red local. SQLite conserva mediciones, energía acumulada, usuarios y eventos. La aplicación envía alertas por correo con una gráfica adjunta.

## Funciones

- Lectura real de voltaje, corriente y potencia. Integración de energía en Wh en el servidor.
- Dashboard con gráfica multiserie, fecha, hora y estados de consumo.
- Estados NORMAL, UNA_CARGA y SIN_CARGA, determinados por corriente total.
- Avisos automáticos por correo y registro de intentos y resultados de envío.
- Visitante de solo lectura, usuarios con correo verificado y acceso de administrador.
- Historial por periodo, episodios de condición anormal y exportación CSV/PDF.
- Inicio automático mediante systemd en la Pi y lanzador con acceso directo en Windows.

Esta entrega conserva la versión con email validada por el autor. Los datos personales y el historial del equipo original se excluyen. La aplicación crea su base de datos local al iniciar.

## Hardware y protocolo

| Elemento | Configuración |
| --- | --- |
| Microcontrolador | Arduino Mega 2560 |
| Sensor | Un INA219 en dirección I²C 0x40 |
| Cargas | Cuatro módulos LED de 12 V en dos grupos con interruptores |
| Pantalla | LCD 16×2 con potenciómetro de contraste |
| LCD RS E D4 D5 D6 D7 | Pines 7 8 9 10 11 12 |
| Amarillo 1 y 2 | Pines 30 y 31 |
| Rojo y azul | Pines 32 y 33 |
| USB serial | 9600 baudios, una línea JSON cada 500 ms aproximadamente |

El INA219 mide el consumo total de ambas ramas. El estado UNA_CARGA expresa consumo reducido, sin identificar cuál rama se apagó. Los LED amarillos representan el estado agregado.

| Estado | Corriente |
| --- | --- |
| SIN_CARGA | Menos de 40 mA |
| UNA_CARGA | Desde 40 hasta menos de 247 mA |
| NORMAL | Desde 247 mA |

El primer estado se toma de la primera lectura. Las transiciones posteriores requieren 2000 ms de confirmación. El LCD alterna cada 3000 ms. Durante el envío, el LED azul cambia cada 250 ms.

Ejemplo de mensaje serial

```json
{"voltage":12.230,"current_ma":332.00,"power_mw":4054.00,"state":"NORMAL"}
```

Python utiliza EMAIL_START, EMAIL_DONE y EMAIL_ERROR para controlar el indicador azul. DONE y ERROR apagan el indicador.

## Programa del Arduino

Abre `arduino/DV_Power_Monitor/DV_Power_Monitor.ino` en Arduino IDE. Selecciona la placa Arduino Mega 2560 y el puerto del equipo. Instala la biblioteca Adafruit INA219 con sus dependencias y LiquidCrystal si tu instalación no la incluye. Compila y carga el sketch. Cierra el Monitor Serie antes de arrancar Python.

El archivo corresponde al código compartido por el autor, con presentación de comentarios y espacios reorganizada. El Arduino del prototipo ya contiene el programa y puede usarse directamente para la demostración.

## Instalación en Windows

1. Instala Python 3.13 con el lanzador `py`. Comprueba en PowerShell `py -3.13 --version`.
2. Descarga y extrae el proyecto completo en una carpeta fija.
3. Conecta el Arduino por USB y alimenta el montaje. Cierra otras ejecuciones que usen el mismo puerto serial o el puerto web 5000.
4. Haz doble clic en `Iniciar_DV_Windows.bat` dentro de la carpeta del proyecto. El primer inicio requiere Internet para crear `.venv_windows` e instalar dependencias.
5. Introduce localmente el remitente Gmail, su contraseña de aplicación y la contraseña del administrador web. Si hay varios puertos, elige el Arduino.
6. Abre `http://127.0.0.1:5000/` en la laptop y deja abierta la consola mientras funcione el servidor.

Para crear el acceso directo, haz clic derecho en el `.bat`, elige Mostrar más opciones, Enviar a y Escritorio crear acceso directo. Conserva el archivo original junto a `main.py` e `iniciar_app.py`.

Para reconfigurar credenciales, detén el monitor con Ctrl+C, abre PowerShell en la carpeta y ejecuta

```powershell
.\Iniciar_DV_Windows.bat --configurar
```

El lanzador guarda las credenciales por usuario en `%LOCALAPPDATA%\DVPowerMonitor\config.json`. Cada equipo nuevo debe crear su propio entorno y configuración. Al trasladar una copia usada, omite `.venv_windows` o renómbrala antes de arrancar.

## Instalación manual en Raspberry Pi

Se probó con Raspberry Pi OS de 64 bits y Python 3.13.5. Coloca el contenido del proyecto en `~/DV_Power_Monitor_Actual`.

```bash
cd ~/DV_Power_Monitor_Actual
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ls -l /dev/serial/by-id/
```

Si falta el módulo venv, instala `python3-venv` con apt. En `main.py`, ajusta el argumento `port` de `SerialReader` a la ruta USB que muestra tu Pi. Mantén 9600 baudios. El respaldo conserva el identificador del Arduino original. Windows sustituye esa ruta al elegir el COM desde su lanzador.

Antes del inicio manual, configura las variables en esa terminal. El siguiente bloque pide las claves sin mostrarlas.

```bash
read -r -p 'Correo remitente: ' DV_EMAIL_USER
export DV_EMAIL_USER
read -r -s -p 'Contraseña de aplicación Gmail: ' DV_EMAIL_PASSWORD
printf '\n'
export DV_EMAIL_PASSWORD
read -r -s -p 'Contraseña administrador web: ' DV_ADMIN_PASSWORD
printf '\n'
export DV_ADMIN_PASSWORD
export DV_SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python iniciar_app.py
```

Configura los destinatarios generales desde la interfaz del administrador. Los usuarios deben verificar su correo para recibir avisos personales. Tener una cuenta o navegador cerrado no impide recibir esos avisos mientras el servidor esté funcionando.

Para persistir la configuración con systemd, guarda las variables mediante líneas `export` en `~/.config/dv-power-monitor/entorno.sh` con permisos 600. Los archivos en `config_pi` son las referencias del despliegue original, con usuario `dvmonitor`. Adapta el usuario y las rutas al equipo de destino. Copia `arrancar_pi.sh` a la raíz del proyecto y la unidad a `/etc/systemd/system/dv-power-monitor.service`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dv-power-monitor
systemctl status dv-power-monitor --no-pager
journalctl -u dv-power-monitor -n 50 --no-pager
```

Detén el servidor manual con Ctrl+C antes de activar el servicio.

## Acceso desde otros dispositivos

En la Pi usa `hostname -I`. En Windows usa `ipconfig` y busca la IPv4 del adaptador conectado. En otro equipo de la misma red abre `http://IP_DEL_SERVIDOR:5000/`. Usa también la IP actual al pasar a un hotspot. La línea de inicio que menciona `.153` conserva un mensaje del desarrollo y puede diferir de la IP que Flask muestra como `Running on`.

En la Pi el servicio continúa al cerrar el navegador. En Windows conserva abierta o minimizada la consola. El envío de correo requiere Internet. El dashboard carga Chart.js 4.5.1 desde un CDN, por lo que un navegador sin ese recurso necesita acceso a Internet para cargar las gráficas.

## Archivos principales

| Archivo | Función |
| --- | --- |
| iniciar_app.py | Entrada principal del portal, adquisición y monitor |
| main.py | Coordinación, estados y alertas |
| serial_reader.py | Lectura y validación serial |
| storage.py y episodes.py | SQLite, energía e historial de episodios |
| notifications.py y alert_graph.py | Correo y gráfica adjunta |
| users.py y personal_alerts.py | Cuentas y verificación de correos |
| recipients.py | Destinatarios generales |
| history_page.py y exportaciones.py | Consulta y CSV/PDF |
| iniciar_dashboard.py | Rutas y acceso del administrador |
| templates y static | Interfaz web |
| lanzar_windows.py | Configuración y selección del COM en Windows |

## Pruebas y límites de esta entrega

El autor confirmó lecturas reales, cambios de estado, correo recibido con gráfica, historial, exportación y acceso desde Pi, laptop y celular. También confirmó operación desde el respaldo Windows y acceso con hotspot. La preparación para publicación verificó sintaxis Python y el arranque con una base nueva. No se repitieron pruebas físicas desde el entorno de preparación.

Las mediciones de referencia del desarrollo fueron aproximadamente 12.23 V y 332 mA con dos grupos activos, 12.28 V y 166 mA con un grupo, y 12.38 V con consumo cercano a cero con ambos apagados.

Los reintentos automáticos de correo y la unificación completa de alarmas por voltaje quedaron como mejoras futuras. Esta versión no contiene la ampliación de WhatsApp manual. Las bases de datos de distintas computadoras son independientes. El servidor se utiliza en la red local de la demostración.

## Entrega académica

Para el anexo A.1 del informe, cita la URL del repositorio y el identificador del commit o la versión entregada. Conserva además una copia ZIP de esa misma versión para la evaluación.
