AmigoPet Patch 006 - Avaliações Premium

O que este patch adiciona:
- Tabela ratings no backend.
- Endpoint para cliente avaliar passeador após passeio finalizado.
- Endpoint para passeador avaliar cliente após passeio finalizado.
- Recalculo automático da média de avaliação do usuário avaliado.
- Notificação interna quando uma avaliação é recebida.
- Card visual premium de avaliação no app Cliente.
- Card visual premium de avaliação no app Passeador.
- Atualização de cache/versionamento do PWA.

Arquivos modificados:
- backend/app/main.py
- frontend/index.html
- frontend/app.js
- frontend/passeador.html
- frontend/walker.js
- frontend/pwa.js
- frontend/sw.js
- frontend/styles.css

Como aplicar:
1. Extraia este ZIP dentro de E:\amigopet_app
2. Confirme a substituição dos arquivos.
3. Rode:

cd E:\amigopet_app
git status

git add backend/app/main.py frontend/index.html frontend/app.js frontend/passeador.html frontend/walker.js frontend/pwa.js frontend/sw.js frontend/styles.css

git commit -m "Patch 006 - Avaliacoes Premium"

git push origin main

Teste recomendado:
1. Aguarde o deploy do Render.
2. Abra cliente e passeador com Ctrl+F5.
3. Crie um passeio, confirme pagamento, aceite, inicie e finalize.
4. No app Cliente, deve aparecer o card para avaliar o passeador.
5. No app Passeador, deve aparecer o card para avaliar o cliente.
6. Envie avaliação e confirme se a nota média do usuário atualiza.

Observação:
A avaliação só aparece para passeio com status finalizado.
