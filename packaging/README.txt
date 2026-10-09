AURA 1.0 - WiZ light control from your PC
=========================================

English first. El texto en español está más abajo.

Aura controls your WiZ lights over your home network, without the phone
app and without going through the internet.


GETTING STARTED
---------------
1. Extract the whole "Aura" folder from the .zip (right-click, "Extract
   All"). It will not run from inside the .zip.
2. Open Aura.exe. There is nothing to install.
3. The first time, it looks for your lights on its own. If it finds one,
   you are ready. If there are several, pick the one you want to control.

The PC and the light must be on the same Wi-Fi.

If Windows shows "Windows protected your PC", that is because the program
is not signed: click "More info", then "Run anyway". If it asks about
network access, allow it on private networks.

The interface is in English by default. To switch to Spanish, open
Settings (the sliders icon, top left) and choose "Español".


TURNING THE LIGHT ON AND OFF QUICKLY
------------------------------------
- The big circle in the window. The ring of dots around it is the
  brightness: drag it, click it, or use the mouse wheel over the
  circle. Each switch sounds like a key on a mechanical keyboard.
  They are real recordings of 13 switches: in Settings > Sound, click
  one to hear it and keep the one you like (or None). To use your own,
  choose Custom and put on.wav (and off.wav) in data\sounds.
- Ctrl + Alt + L from any app.
- One click on Aura's icon next to the clock. On Windows 11 it may be
  hidden under the "^" arrow: drag it onto the taskbar to keep it visible.
- The space bar, while Aura's window is in front.

Closing the window leaves Aura in the tray so shortcuts and routines keep
working. To quit completely: right-click the icon, "Quit".


KEYBOARD SHORTCUTS (work from any app)
--------------------------------------
  Ctrl + Alt + L            turn on and off
  Ctrl + Alt + Page Up      brighter
  Ctrl + Alt + Page Down    dimmer
  Ctrl + Alt + K            next favorite (colors first, then whites)

Change them in Settings > Shortcuts.


WHAT IS INSIDE
--------------
Color      Color wheel, hex code and favorites.
White      From candlelight (2200 K) to cool light (6500 K), with favorites.
Scenes     Your own scenes: two to four colors and a pace, and the light
           glides between them. Aura has to stay open for these.
           Plus the 28 scenes built into the light, which keep running
           after you close Aura.
Effects    Music: the light reacts to what your PC is playing (or to the
           microphone), in six modes.
           Screen: the light mirrors the colors on your screen, like
           Ambilight. Aura has to stay open for these two.
Routines   Sleep timer: dims the light little by little, then turns it
           off (15, 30, 45 or 60 minutes).
           Wake-up light: rises slowly and reaches full brightness at the
           time you set, every day or on weekdays.
           Follow the time of day: cool white by day, warm at night.
           Follow this PC: off when the PC locks or goes to sleep, back
           on when you return.
           Routines run while Aura is open; the tray is enough.

"Strobe" mode produces fast flashes. Avoid it if flashing lights affect
you or anyone nearby.


STARTING WITH WINDOWS
---------------------
Settings > General > "Start with Windows" opens Aura in the tray when you
sign in, so shortcuts and routines are ready without opening it yourself.


COMMANDS FOR DESKTOP SHORTCUTS
------------------------------
  Aura.exe --toggle    turn on or off
  Aura.exe --on        turn on
  Aura.exe --off       turn off
  Aura.exe --hidden    start straight in the tray


IT IS PORTABLE
--------------
Everything stays inside this folder: settings are saved in "data". You can
move the whole folder to another drive or a USB stick and it keeps working.
The only thing written outside the folder is the "Start with Windows"
entry in the registry, and only while that switch is on. To uninstall,
turn that switch off and delete the folder.


IF SOMETHING DOES NOT WORK
--------------------------
It cannot find the light
    Check that it has power and that the PC is on the same Wi-Fi (not the
    guest network). If you use a VPN, try disconnecting it. You can also
    add it by hand with its IP address: you can see it in the WiZ phone
    app, in the light's settings.

"Offline"
    If the router gave the light a new address, Aura finds it again on its
    own within a few seconds.

The music effect does not react
    Something has to be playing through Windows' default audio output.
    Try raising "Sensitivity".

A shortcut does nothing
    Another program may be using it. Settings > Shortcuts shows a warning
    next to it; pick a different combination.

Aura does not open
    Look at the file data\error.log. As an alternative, run
    app\start.bat, which starts the program a different way.


TEST STATUS
-----------
Tested by its author on Windows 11 with a WiZ color bulb (E27, RGB and
tunable white, 8 W). Other Windows versions and other WiZ models have
not been tested. The automated tests run against a simulated WiZ light
(protocol, interface, effects, routines). If you find something odd,
the details are in data\error.log, and you can report it at
https://github.com/lvxro/aura/issues


SOURCE CODE AND LICENSE
-----------------------
The program is in the "app" folder, in Python: you can read and modify it.
The full project, with the tests and the scripts that build this
package, is at https://github.com/lvxro/aura
It is free software under the GPL-3.0 license (see LICENSE.txt and
CREDITS.txt). It is not an official WiZ or Signify product.



=========================================================================
ESPAÑOL
=========================================================================

AURA 1.0 - control de luces WiZ desde la PC
===========================================

Aura maneja tus luces WiZ por la red de tu casa, sin la app del celular
y sin pasar por internet.


CÓMO EMPEZAR
------------
1. Extraé toda la carpeta "Aura" del .zip (clic derecho, "Extraer todo").
   No funciona si la abrís desde adentro del .zip.
2. Abrí Aura.exe. No hay nada que instalar.
3. La primera vez busca las luces sola. Si encuentra una, queda lista.
   Si hay varias, elegí cuál querés controlar.

La PC y la luz tienen que estar en el mismo Wi-Fi.

Si Windows muestra "Windows protegió su PC" es porque el programa no está
firmado: tocá "Más información" y después "Ejecutar de todas formas".
Si pregunta por el acceso a la red, permitilo en redes privadas.

La interfaz arranca en inglés. Para pasarla a español, abrí Settings (el
ícono de los controles deslizantes, arriba a la izquierda) y elegí
"Español".


PRENDER Y APAGAR RÁPIDO
-----------------------
- El círculo grande de la ventana. El anillo de puntos que lo rodea es
  el brillo: arrastralo, hacele clic o usá la rueda del mouse sobre el
  círculo. Cada cambio suena como una tecla de teclado mecánico. Son
  grabaciones reales de 13 switches: en Ajustes > Sonido hacé clic en
  uno para escucharlo y quedate con el que te guste (o Ninguno). Para
  usar uno tuyo, elegí Propio y poné on.wav (y off.wav) en data\sounds.
- Ctrl + Alt + L desde cualquier programa.
- Un clic en el ícono de Aura al lado del reloj. En Windows 11 puede estar
  escondido en la flechita "^": arrastralo a la barra para tenerlo a la vista.
- La barra espaciadora, con la ventana de Aura al frente.

Al cerrar la ventana, Aura sigue en la bandeja para que los atajos y las
rutinas funcionen. Para salir del todo: clic derecho en el ícono, "Salir".


ATAJOS DE TECLADO (funcionan desde cualquier programa)
------------------------------------------------------
  Ctrl + Alt + L            prender y apagar
  Ctrl + Alt + Re Pág       más brillo
  Ctrl + Alt + Av Pág       menos brillo
  Ctrl + Alt + K            siguiente favorito (primero colores, después blancos)

Se cambian en Ajustes > Atajos.


QUÉ TRAE
--------
Color      Rueda de color, código hexadecimal y favoritos.
Blanco     De luz de vela (2200 K) a luz fría (6500 K), con favoritos.
Escenas    Tus propias escenas: de dos a cuatro colores y una velocidad, y
           la luz va pasando entre ellos. Para estas Aura tiene que
           quedar abierta.
           Además, las 28 escenas de fábrica de la luz, que siguen
           andando aunque cierres Aura.
Efectos    Música: la luz reacciona a lo que suena en la PC (o al
           micrófono), con seis modos.
           Pantalla: la luz copia los colores de la pantalla, como un
           Ambilight. Para estos dos Aura tiene que quedar abierta.
Rutinas    Apagado para dormir: baja la luz de a poco y después la
           apaga (15, 30, 45 o 60 minutos).
           Amanecer: sube despacio y llega al brillo máximo a la hora que
           pongas, todos los días o de lunes a viernes.
           Seguir la hora del día: blanco frío de día, cálido de noche.
           Seguir a la PC: se apaga cuando la PC se bloquea o se suspende,
           y se prende cuando volvés.
           Las rutinas funcionan mientras Aura esté abierta; alcanza con
           que esté en la bandeja.

El modo "Estrobo" produce destellos rápidos. Evitalo si a vos o a alguien
que esté cerca le afectan las luces intermitentes.


ARRANCAR CON WINDOWS
--------------------
Ajustes > General > "Iniciar con Windows" abre Aura en la bandeja al
iniciar sesión, así los atajos y las rutinas quedan listos sin abrirla.


ÓRDENES PARA ACCESOS DIRECTOS
-----------------------------
  Aura.exe --toggle    prende o apaga
  Aura.exe --on        prende
  Aura.exe --off       apaga
  Aura.exe --hidden    arranca directo en la bandeja


ES PORTABLE
-----------
Todo queda dentro de esta carpeta: los ajustes se guardan en "data".
Podés mover la carpeta entera a otro disco o a un pendrive y sigue igual.
Lo único que se escribe fuera de la carpeta es la entrada de "Iniciar con
Windows" en el registro, y solo mientras ese interruptor esté activado.
Para desinstalar, desactivá ese interruptor y borrá la carpeta.


SI ALGO NO ANDA
---------------
No encuentra la luz
    Revisá que esté enchufada y que la PC esté en el mismo Wi-Fi (no en la
    red de invitados). Si usás una VPN, probá desconectarla. También podés
    agregarla a mano con su dirección IP: la ves en la app WiZ del celular,
    en los ajustes de la luz.

"Sin conexión"
    Si el router le cambió la dirección a la luz, Aura la vuelve a buscar
    sola en unos segundos.

El efecto de música no reacciona
    Tiene que estar sonando algo por la salida de audio predeterminada de
    Windows. Probá subir la "Sensibilidad".

Un atajo no hace nada
    Puede que otro programa lo esté usando. En Ajustes > Atajos aparece un
    aviso al lado; elegí otra combinación.

Aura no abre
    Mirá el archivo data\error.log. Como alternativa, abrí
    app\start.bat, que arranca el programa de otra forma.


ESTADO DE LAS PRUEBAS
---------------------
Probada por su autor en Windows 11 con un foco WiZ color (E27, RGB y
blanco regulable, 8 W). Otras versiones de Windows y otros modelos WiZ
no se probaron. Las pruebas automáticas corren contra una luz WiZ
simulada (protocolo, interfaz, efectos, rutinas). Si encontrás algo
raro, el detalle queda en data\error.log, y lo podés reportar en
https://github.com/lvxro/aura/issues


CÓDIGO FUENTE Y LICENCIA
------------------------
El programa está en la carpeta "app", en Python: se puede leer y modificar.
El proyecto completo, con las pruebas y los scripts que arman este
paquete, está en https://github.com/lvxro/aura
Es software libre bajo licencia GPL-3.0 (ver LICENSE.txt y CREDITS.txt).
No es un producto oficial de WiZ ni de Signify.
