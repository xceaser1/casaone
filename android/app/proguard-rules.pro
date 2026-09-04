# Regles de reduction de code (R8).
#
# minifyEnabled est laisse a false : le pont JavaScript est le point fragile.
# R8 supprime les methodes qu'il croit inutilisees, or celles du pont ne sont
# appelees que depuis la page web — il ne peut pas le voir. L'application
# compilerait, s'installerait, et le scanner natif cesserait silencieusement de
# repondre. Les regles ci-dessous sont donc prêtes AVANT d'activer R8.

# Pont expose au WebView : ne jamais renommer ni supprimer.
-keepclassmembers class com.urbagec.casaone.MainActivity$Pont {
    public *;
}
-keepattributes JavascriptInterface
-keep class * implements android.webkit.JavascriptInterface { *; }

# Workers instancies par reflexion par WorkManager.
-keep class com.urbagec.casaone.Veille { <init>(...); }

# Fournisseur de tuile instancie par le systeme.
-keep class com.urbagec.casaone.WidgetChantier { *; }
