!define APP_NAME      "AgendadorCitas"
!define APP_VERSION   "1.0"
!define INSTALL_DIR   "$PROGRAMFILES\${APP_NAME}"
!define DIST_DIR      "dist\automation"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "Setup_${APP_NAME}.exe"
InstallDir "${INSTALL_DIR}"
RequestExecutionLevel admin

Page directory            ; permitir elegir carpeta
Page instfiles            ; mostrar progreso

Section "Instalar ${APP_NAME}" SecMain
  ; 1) Copiar el ejecutable y librerías Python
  SetOutPath "${INSTALL_DIR}"
  File /r "${DIST_DIR}\*.*"

  ; 2) Copiar chromedriver
  File /r "chromedriver-win64\*.*"

  ; 3) Copiar recursos web y plantillas
  File /r "static\*.*"
  File /r "templates\*.*"
  File /r "instance\*.*"

  ; 4) Copiar dump de PostgreSQL
  File "dump_myapp"

  ; 5) (Opcional) Crear acceso directo en Escritorio
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "${INSTALL_DIR}\automation.exe"

  ; 6) Restaurar base de datos (requiere pg_restore en PATH o indicar ruta completa)
  ;    Le pedirá contraseña al usuario
  ExecWait '"C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" -U postgres -d agendador_citas -W -v "${INSTALL_DIR}\dump_myapp"'

SectionEnd
