RESTAURAÇÃO EMERGENCIAL DO PASSEADOR

Este patch restaura somente:
- frontend/passeador.html
- frontend/walker.js
- frontend/styles.css
- frontend/assets/amigopet-banner.png

Não mexe no backend.
Não mexe no cliente.
Não mexe no PIX.
Não mexe no banco.

Aplicar:
cd E:\amigopet_app

git add frontend/passeador.html frontend/walker.js frontend/styles.css frontend/assets/amigopet-banner.png
git commit -m "Restaurar login do passeador"
git push

Depois aguarde o Render ficar Live e teste /passeador.
