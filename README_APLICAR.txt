AmigoPet Patch 002 - Passeador somente Google + Termo robusto

Arquivos alterados:
- backend/app/main.py
- frontend/passeador.html
- frontend/walker.js
- frontend/styles.css

Correções:
1. Tela do passeador mostra somente o botão Entrar com Google.
2. Remove visualmente formulário antigo, preencher conta teste, esqueci senha e criar conta manual.
3. Passeador que já tinha feito login antes agora também é obrigado a aceitar o termo.
4. O frontend recarrega a sessão do servidor para buscar accepted_terms, accepted_terms_at e terms_version.
5. Se não aceitar, não libera Pedidos/Perfil/Mapa.
6. Cache bust atualizado para walker-terms-v2.

Aplicar:
1. Extraia este ZIP dentro de E:\amigopet_app substituindo os arquivos.
2. Rode:

cd E:\amigopet_app
git add backend/app/main.py frontend/passeador.html frontend/walker.js frontend/styles.css
git commit -m "Ajustar login Google e aceite de termos do passeador"
git push

Depois do deploy, teste em aba anônima ou limpe o cache do navegador.
