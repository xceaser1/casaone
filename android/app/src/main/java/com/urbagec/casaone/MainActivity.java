package com.urbagec.casaone;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.text.InputType;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.SslErrorHandler;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.Toast;

/**
 * CASA ONE — coque applicative Android.
 *
 * L'interface (navigation, onglets, transitions) reste fournie par le web :
 * une seule interface a maintenir, et tout changement de design se deploie
 * cote serveur sans reinstaller l'application. C'est aussi pourquoi la coque
 * n'ajoute PAS sa propre barre d'onglets : elle ferait doublon avec celle que
 * la page affiche deja sur telephone.
 *
 * Elle apporte en revanche ce qu'un navigateur ne sait pas faire :
 *   - scanner de badges natif (ML Kit), appele depuis la page web ;
 *   - verification periodique en tache de fond et notifications ;
 *   - tuile d'ecran d'accueil et raccourcis a l'appui long ;
 *   - controle de version au demarrage ;
 *   - telechargement et partage natif des exports ;
 *   - plein ecran bord a bord et certificat auto-signe du serveur de chantier.
 */
public class MainActivity extends Activity {

    static final String PREFS = "casaone";
    static final String KEY_URL = "server_url";

    private static final int REQ_CAM = 101;
    private static final int REQ_NOTIF = 102;
    private static final int REQ_FICHIER = 200;
    private static final int REQ_SCAN = 300;

    private WebView web;
    private ProgressBar progress;
    private View offline;
    private SharedPreferences prefs;
    private boolean erreurChargement = false;
    private ValueCallback<Uri[]> retourFichier;
    /** Nom de la fonction JS a rappeler avec le badge lu. */
    private String rappelScan;

    @Override
    protected void onCreate(Bundle etat) {
        setTheme(R.style.AppTheme);
        super.onCreate(etat);
        try {
            pleinEcran();
            setContentView(R.layout.main);
            prefs = getSharedPreferences(PREFS, MODE_PRIVATE);

            web = (WebView) findViewById(R.id.web);
            progress = (ProgressBar) findViewById(R.id.progress);
            offline = findViewById(R.id.offline);
            View retry = findViewById(R.id.retry);
            if (retry != null) {
                retry.setOnClickListener(new View.OnClickListener() {
                    @Override public void onClick(View v) { masquerHorsLigne(); charger(null); }
                });
            }
            View changer = findViewById(R.id.changer_adresse);
            if (changer != null) {
                changer.setOnClickListener(new View.OnClickListener() {
                    @Override public void onClick(View v) { demanderUrl(false); }
                });
            }

            configurerWebView();
            demanderAutorisations();
            Veille.programmer(this);

            if (prefs.getString(KEY_URL, null) == null) {
                demanderUrl(true);
            } else {
                charger(cheminDemande(getIntent()));
                VerificationVersion.lancer(this);
            }
        } catch (Throwable t) {
            new AlertDialog.Builder(this)
                .setTitle("Erreur au démarrage")
                .setMessage(String.valueOf(t))
                .setPositiveButton("OK", null).show();
        }
    }

    /** Un raccourci, une tuile ou une notification demande une page precise. */
    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        String chemin = cheminDemande(intent);
        if (chemin != null) charger(chemin);
    }

    private String cheminDemande(Intent intent) {
        return intent == null ? null : intent.getStringExtra("chemin");
    }

    private void demanderAutorisations() {
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.CAMERA}, REQ_CAM);
        }
        // Android 13+ : les notifications doivent etre autorisees explicitement.
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                   != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQ_NOTIF);
        }
    }

    /** Affichage bord a bord : le web gere les encoches via safe-area-inset. */
    private void pleinEcran() {
        Window w = getWindow();
        if (Build.VERSION.SDK_INT >= 30) {
            w.setDecorFitsSystemWindows(false);
        } else {
            w.getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
        }
        w.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        w.setStatusBarColor(0x00000000);
        w.setNavigationBarColor(0x00000000);
    }

    String base() {
        return prefs.getString(KEY_URL, BuildConfig.URL_DEFAUT).replaceAll("/+$", "");
    }

    private void charger(String chemin) {
        web.loadUrl(base() + (chemin != null ? chemin : "/dashboard"));
    }

    private void masquerHorsLigne() {
        if (offline != null) offline.setVisibility(View.GONE);
        erreurChargement = false;
    }

    // ------------------------------------------------------------ WebView
    private void configurerWebView() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(true);
        s.setSupportZoom(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true);

        web.addJavascriptInterface(new Pont(), "CasaOneNatif");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedSslError(WebView v, SslErrorHandler handler, SslError err) {
                // Le serveur de chantier presente un certificat auto-signe : on
                // ne passe outre que pour une adresse privee ou Tailscale.
                // Sur un domaine public (Render), une erreur de certificat est
                // un vrai signal d'alerte et doit rester bloquante — sinon la
                // coque accepterait n'importe quel certificat, pour n'importe
                // quel hote, et l'interception deviendrait triviale.
                String hote = null;
                try {
                    hote = Uri.parse(err.getUrl()).getHost();
                } catch (Throwable ignore) { }
                if (Reseau.adressePrivee(hote)) {
                    handler.proceed();
                } else {
                    handler.cancel();
                }
            }
            @Override
            public void onPageStarted(WebView v, String url, Bitmap favicon) {
                erreurChargement = false;
            }
            @Override
            public void onPageFinished(WebView v, String url) {
                if (!erreurChargement && offline != null) offline.setVisibility(View.GONE);
            }
            @Override
            public void onReceivedError(WebView v, WebResourceRequest req, WebResourceError err) {
                // Quand le service worker sert une page depuis son cache, aucune
                // erreur ne remonte : cet ecran ne masque donc pas le hors-ligne.
                if (req.isForMainFrame() && offline != null) {
                    erreurChargement = true;
                    offline.setVisibility(View.VISIBLE);
                    android.widget.TextView adresse =
                        (android.widget.TextView) findViewById(R.id.adresse_essayee);
                    if (adresse != null) adresse.setText(base());
                }
            }
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                Uri u = req.getUrl();
                if (u.getScheme() != null && !u.getScheme().startsWith("http")) {
                    return ouvrirDehors(u);
                }
                if (u.getHost() != null && !base().contains(u.getHost())) {
                    return ouvrirDehors(u);
                }
                return false;
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(new Runnable() {
                    @Override public void run() { request.grant(request.getResources()); }
                });
            }
            @Override
            public void onProgressChanged(WebView v, int p) {
                if (progress == null) return;
                progress.setProgress(p);
                progress.setVisibility(p < 100 ? View.VISIBLE : View.GONE);
            }
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> retour,
                                             FileChooserParams params) {
                retourFichier = retour;
                try {
                    startActivityForResult(params.createIntent(), REQ_FICHIER);
                    return true;
                } catch (ActivityNotFoundException e) {
                    retourFichier = null;
                    return false;
                }
            }
        });

        web.setDownloadListener(new DownloadListener() {
            @Override
            public void onDownloadStart(String url, String agent, String disposition,
                                        String mime, long taille) {
                try {
                    String nom = URLUtil.guessFileName(url, disposition, mime);
                    DownloadManager.Request r = new DownloadManager.Request(Uri.parse(url));
                    r.setMimeType(mime);
                    r.addRequestHeader("Cookie", CookieManager.getInstance().getCookie(url));
                    r.setTitle(nom);
                    r.setNotificationVisibility(
                        DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                    r.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, nom);
                    ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(r);
                    Toast.makeText(MainActivity.this, "Téléchargement : " + nom,
                        Toast.LENGTH_LONG).show();
                } catch (Throwable t) {
                    Toast.makeText(MainActivity.this, "Téléchargement impossible",
                        Toast.LENGTH_SHORT).show();
                }
            }
        });
    }

    private boolean ouvrirDehors(Uri u) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, u));
            return true;
        } catch (ActivityNotFoundException e) {
            return false;
        }
    }

    // ------------------------------------------------------- Pont JavaScript
    /**
     * Passerelle appelee par la page web.
     *
     * Un pont ouvert a n'importe quel contenu donnerait a une page tierce
     * l'acces a la camera et au partage : les methodes sensibles verifient donc
     * que la page appelante provient bien du serveur configure.
     */
    private class Pont {

        private boolean origineSure() {
            try {
                // Le pont est appele depuis le fil JavaScript, mais getUrl()
                // doit etre lu sur le fil principal.
                final String[] url = new String[1];
                final Object verrou = new Object();
                synchronized (verrou) {
                    runOnUiThread(new Runnable() {
                        @Override public void run() {
                            synchronized (verrou) {
                                url[0] = web.getUrl();
                                verrou.notifyAll();
                            }
                        }
                    });
                    verrou.wait(500);
                }
                return url[0] != null && url[0].startsWith(base());
            } catch (Throwable t) {
                return false;
            }
        }

        /** Ouvre le scanner natif ; le badge lu repart vers `window[rappel](texte)`. */
        @JavascriptInterface
        public void scanner(String rappel) {
            if (!origineSure()) return;
            rappelScan = rappel;
            startActivityForResult(new Intent(MainActivity.this, ScannerActivity.class), REQ_SCAN);
        }

        /** Permet a la page de savoir qu'elle peut se passer de jsQR. */
        @JavascriptInterface
        public boolean scannerDisponible() {
            return true;
        }

        @JavascriptInterface
        public int versionApp() {
            return BuildConfig.VERSION_CODE;
        }

        /** Feuille de partage Android (export, lien de badge...). */
        @JavascriptInterface
        public void partager(String texte) {
            if (!origineSure()) return;
            Intent i = new Intent(Intent.ACTION_SEND);
            i.setType("text/plain");
            i.putExtra(Intent.EXTRA_TEXT, texte);
            startActivity(Intent.createChooser(i, "Partager"));
        }
    }

    @Override
    protected void onActivityResult(int code, int resultat, Intent data) {
        if (code == REQ_FICHIER && retourFichier != null) {
            retourFichier.onReceiveValue(
                WebChromeClient.FileChooserParams.parseResult(resultat, data));
            retourFichier = null;
            return;
        }
        if (code == REQ_SCAN) {
            if (resultat == RESULT_OK && data != null && rappelScan != null) {
                String texte = data.getStringExtra("texte");
                if (texte != null) {
                    String echappe = texte.replace("\\", "\\\\").replace("'", "\\'")
                                          .replace("\n", "").replace("\r", "");
                    web.evaluateJavascript(
                        "window['" + rappelScan + "'] && window['" + rappelScan
                        + "']('" + echappe + "')", null);
                }
            }
            rappelScan = null;
            return;
        }
        super.onActivityResult(code, resultat, data);
    }

    // ------------------------------------------------------ Adresse serveur
    private void demanderUrl(final boolean premier) {
        final EditText champ = new EditText(this);
        champ.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        champ.setText(prefs.getString(KEY_URL, BuildConfig.URL_DEFAUT));
        new AlertDialog.Builder(this)
            .setTitle("Adresse du serveur")
            .setMessage("Exemple : https://casaone.onrender.com")
            .setView(champ)
            .setCancelable(!premier)
            .setPositiveButton("OK", new DialogInterface.OnClickListener() {
                @Override public void onClick(DialogInterface d, int w) {
                    String u = champ.getText().toString().trim();
                    if (!u.startsWith("http")) u = "https://" + u;
                    prefs.edit().putString(KEY_URL, u).apply();
                    masquerHorsLigne();
                    charger(null);
                    VerificationVersion.lancer(MainActivity.this);
                }
            }).show();
    }

    // L'adresse doit rester modifiable en permanence, pas seulement depuis
    // l'ecran d'erreur : un serveur peut changer d'adresse sans que
    // l'application soit en panne.
    @Override
    public boolean onCreateOptionsMenu(android.view.Menu menu) {
        menu.add(0, 1, 0, "Adresse du serveur");
        menu.add(0, 2, 0, "Recharger");
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(android.view.MenuItem item) {
        if (item.getItemId() == 1) { demanderUrl(false); return true; }
        if (item.getItemId() == 2) { masquerHorsLigne(); charger(null); return true; }
        return super.onOptionsItemSelected(item);
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
}
