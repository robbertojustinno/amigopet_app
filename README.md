# AmigoPet Android Studio

Projeto com 2 APKs WebView:

- cliente: abre a URL configurada do backend/web
- passeador: abre a URL configurada do backend/web em `/passeador`

## Abrir no Android Studio

1. Extraia este ZIP.
2. Abra o Android Studio.
3. Clique em Open.
4. Selecione a pasta amigopet_android_webview.
5. Aguarde o Gradle sincronizar.
6. Escolha o módulo `cliente` ou `passeador`.
7. Clique em Run.

## Gerar APK

Menu:

Build > Build Bundle(s) / APK(s) > Build APK(s)

Ou terminal:

```bash
gradlew :cliente:assembleDebug
gradlew :passeador:assembleDebug
```
