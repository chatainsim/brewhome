' BrewHome - Lancement silencieux (sans fenetre console)
' Double-cliquez sur ce fichier pour demarrer BrewHome en arriere-plan.

Dim fso, scriptDir, batPath, shell

Set fso       = CreateObject("Scripting.FileSystemObject")
Set shell     = CreateObject("WScript.Shell")

' Répertoire du script VBS
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Lancer Flask via pythonw (pas de fenetre console)
Dim pythonw, appPy
pythonw = scriptDir & "\venv\Scripts\pythonw.exe"
appPy   = scriptDir & "\app.py"

If Not fso.FileExists(pythonw) Then
    MsgBox "Environnement virtuel introuvable." & vbCrLf & _
           "Lancez install.bat d'abord.", vbExclamation, "BrewHome"
    WScript.Quit 1
End If

' Lancer en arriere-plan (0 = fenetre cachee)
shell.Run """" & pythonw & """ """ & appPy & """", 0, False

' Ouvrir le navigateur apres 1,5 s
WScript.Sleep 1500
shell.Run "http://localhost:5000"

Set shell = Nothing
Set fso   = Nothing
