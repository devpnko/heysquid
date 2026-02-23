# heysquid Demo — VHS Tape

Output "assets/demo.gif"

Set Shell "bash"
Set FontSize 15
Set Width 880
Set Height 520
Set Padding 16
Set Theme { "name": "Squid", "black": "#0a0e27", "red": "#ff6b9d", "green": "#26de81", "yellow": "#ffd32a", "blue": "#4c6ef5", "magenta": "#bb88ff", "cyan": "#00d4ff", "white": "#e8eaed", "brightBlack": "#5c6370", "brightRed": "#ff6b9d", "brightGreen": "#26de81", "brightYellow": "#ffd32a", "brightBlue": "#4c6ef5", "brightMagenta": "#bb88ff", "brightCyan": "#00d4ff", "brightWhite": "#ffffff", "background": "#0a0e27", "foreground": "#e8eaed", "cursor": "#00d4ff", "selection": "#1e2952" }
Set TypingSpeed 0
Set CursorBlink false

Sleep 500ms
Type "python3 scripts/demo_render.py"
Enter
Sleep 40s
