; StormFuse NSIS installer script (§12.2)
; Requires NSIS 3.x with MultiUser plugin

!define APP_NAME "StormFuse"
; APP_VERSION is defined in the generated build/version.nsh (written by stormfuse.spec).
; Never hardcode the version here — change src/stormfuse/config.py:APP_VERSION instead.
!include "..\version.nsh"
!define APP_PUBLISHER "Winds of Storm"
!define APP_URL "https://github.com/winds-of-storm/stormfuse"
!define INSTALLER_NAME "StormFuse-Setup-${APP_VERSION}.exe"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
!define REG_KEY "Software\StormFuse"
!define DIST_DIR "..\..\dist\StormFuse"

; MultiUser settings
!define MULTIUSER_EXECUTIONLEVEL Highest
!define MULTIUSER_MUI
!define MULTIUSER_INSTALLMODE_COMMANDLINE
!include MultiUser.nsh
!include MUI2.nsh
!include LogicLib.nsh
!include nsDialogs.nsh

!define MUI_ICON "..\..\resources\icons\stormfuse.ico"
!define MUI_UNICON "..\..\resources\icons\stormfuse.ico"

!define MUI_COMPONENTSPAGE_SMALLDESC

Var RemoveAppDataCheckbox
Var RemoveAppDataState

Name "${APP_NAME} ${APP_VERSION}"
OutFile "..\..\dist\${INSTALLER_NAME}"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "${REG_KEY}" "InstallDir"
RequestExecutionLevel admin

; MUI Pages
!insertmacro MUI_PAGE_LICENSE "..\..\LICENSE"
!insertmacro MULTIUSER_PAGE_INSTALLMODE
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
UninstPage custom un.RemoveAppDataPage un.RemoveAppDataPageLeave
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "StormFuse (required)" SEC01
    SectionIn RO
    SetOutPath "$INSTDIR"
    File /r "${DIST_DIR}\*.*"

    ; Registry
    WriteRegStr HKLM "${REG_KEY}" "Version" "${APP_VERSION}"
    WriteRegStr HKLM "${REG_KEY}" "InstallDir" "$INSTDIR"

    ; Add/Remove Programs
    WriteRegStr HKLM "${UNINST_KEY}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKLM "${UNINST_KEY}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKLM "${UNINST_KEY}" "Publisher" "${APP_PUBLISHER}"
    WriteRegStr HKLM "${UNINST_KEY}" "URLInfoAbout" "${APP_URL}"
    WriteRegStr HKLM "${UNINST_KEY}" "UninstallString" "$INSTDIR\Uninstall.exe"
    WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
    WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1

    ; Uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Start menu shortcut
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\StormFuse.exe"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section /o "Desktop shortcut" SEC02
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\StormFuse.exe"
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC01} "Install StormFuse, bundled FFmpeg tools, and Start Menu shortcuts."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC02} "Create a Desktop shortcut."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function un.RemoveAppDataPage
    nsDialogs::Create 1018
    Pop $0
    ${If} $0 == error
        Abort
    ${EndIf}

    ${NSD_CreateLabel} 0 0 100% 24u "StormFuse can also remove application data stored in $LOCALAPPDATA\${APP_NAME}, including logs and future settings."
    Pop $0
    ${NSD_CreateCheckbox} 0 34u 100% 12u "&Remove application data"
    Pop $RemoveAppDataCheckbox
    ${NSD_SetState} $RemoveAppDataCheckbox ${BST_UNCHECKED}

    nsDialogs::Show
FunctionEnd

Function un.RemoveAppDataPageLeave
    ${NSD_GetState} $RemoveAppDataCheckbox $RemoveAppDataState
FunctionEnd

Section "Uninstall"
    RMDir /r "$INSTDIR"
    Delete "$DESKTOP\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"
    RMDir "$SMPROGRAMS\${APP_NAME}"
    DeleteRegKey HKLM "${UNINST_KEY}"
    DeleteRegKey HKLM "${REG_KEY}"
    ${If} $RemoveAppDataState == ${BST_CHECKED}
        RMDir /r "$LOCALAPPDATA\${APP_NAME}"
    ${EndIf}
SectionEnd
