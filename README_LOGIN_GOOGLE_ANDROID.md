# AmigoPet Android — Login Google nativo

Este projeto foi ajustado para o botão **Entrar com Google** funcionar dentro do APK, sem abrir OAuth dentro da WebView.

## O que foi alterado

- Cliente: `cliente/src/main/java/com/rovix/amigopet/cliente/MainActivity.java`
- Passeador: `passeador/src/main/java/com/rovix/amigopet/passeador/MainActivity.java`
- Gradle dos dois apps com `play-services-auth`
- Backend ativo `backend/app/main.py` com as rotas Android:
  - `GET /api/auth/google/android-config`
  - `POST /api/auth/google/android`

## Antes de gerar o APK

No Render, confirme:

```env
GOOGLE_CLIENT_ID=seu_client_id_web_do_google
GOOGLE_CLIENT_SECRET=seu_client_secret
GOOGLE_REDIRECT_URI=https://seu-dominio.com/api/auth/google/callback
```

## Google Cloud obrigatório para APK

No Google Cloud, crie também credenciais OAuth do tipo **Android** para os dois pacotes:

```txt
com.rovix.amigopet.cliente
com.rovix.amigopet.passeador
```

Use o SHA-1 da máquina onde você vai gerar o APK debug:

```powershell
keytool -list -v -keystore "$env:USERPROFILE\.android\debug.keystore" -alias androiddebugkey -storepass android -keypass android
```

Sem essa credencial Android, o Google pode retornar erro 10/DEVELOPER_ERROR.

## Como abrir

Abra a pasta `amigopet_android_webview` no Android Studio.

Depois gere:

```txt
Build > Build Bundle(s) / APK(s) > Build APK(s)
```

Módulos:

- `cliente`
- `passeador`
