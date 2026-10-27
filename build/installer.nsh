!macro customInstall
  CreateDirectory "$APPDATA\Lead Extractor"
  MessageBox MB_YESNO|MB_ICONQUESTION "Enable Google Chrome integration?$\r$\n$\r$\nThis lets Lead Extractor open a dedicated Chrome profile for public Maps and manual source review. It does not import your normal Chrome profile, passwords, or cookies. You can still change this per search." IDYES chrome_integration_yes IDNO chrome_integration_no

  chrome_integration_yes:
    FileOpen $0 "$APPDATA\Lead Extractor\installer-preferences.json" w
    FileWrite $0 '{"chromeIntegration":true}'
    FileClose $0
    Goto chrome_integration_done

  chrome_integration_no:
    FileOpen $0 "$APPDATA\Lead Extractor\installer-preferences.json" w
    FileWrite $0 '{"chromeIntegration":false}'
    FileClose $0

  chrome_integration_done:
!macroend
