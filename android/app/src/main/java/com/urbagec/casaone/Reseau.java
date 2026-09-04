package com.urbagec.casaone;

import android.content.Context;
import android.content.SharedPreferences;
import android.webkit.CookieManager;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.cert.X509Certificate;

import javax.net.ssl.HostnameVerifier;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSession;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

/**
 * Appels JSON vers le serveur CASA ONE, hors WebView.
 *
 * Sert la tuile d'ecran d'accueil, la veille en tache de fond et le controle
 * de version. Reutilise les cookies du WebView : l'utilisateur reste connecte
 * dans l'application, la tache de fond herite donc de sa session.
 */
final class Reseau {

    private Reseau() { }

    static String base(Context c) {
        SharedPreferences p = c.getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE);
        return p.getString(MainActivity.KEY_URL, BuildConfig.URL_DEFAUT).replaceAll("/+$", "");
    }

    /**
     * Le serveur de chantier presente un certificat auto-signe.
     *
     * On ne desactive la verification QUE pour les adresses privees et
     * Tailscale, jamais pour un domaine public : sur Internet, une erreur de
     * certificat est un vrai signal d'alerte et doit rester bloquante.
     */
    static boolean adressePrivee(String hote) {
        if (hote == null) return false;
        return hote.equals("localhost")
            || hote.startsWith("10.")
            || hote.startsWith("192.168.")
            || hote.startsWith("127.")
            || hote.startsWith("100.")            // Tailscale (100.64.0.0/10)
            || hote.matches("^172\\.(1[6-9]|2[0-9]|3[01])\\..*");
    }

    /** Recupere un objet JSON. Renvoie null en cas d'echec, sans lever. */
    static JSONObject json(Context c, String chemin) {
        HttpURLConnection co = null;
        try {
            URL url = new URL(base(c) + chemin);
            co = (HttpURLConnection) url.openConnection();

            if (co instanceof HttpsURLConnection && adressePrivee(url.getHost())) {
                appliquerCertificatChantier((HttpsURLConnection) co);
            }

            co.setConnectTimeout(8000);
            co.setReadTimeout(8000);
            co.setRequestProperty("Accept", "application/json");
            String cookies = CookieManager.getInstance().getCookie(base(c));
            if (cookies != null) co.setRequestProperty("Cookie", cookies);

            if (co.getResponseCode() != 200) return null;
            String type = co.getContentType();
            // Une session expiree renvoie la page de connexion, pas du JSON.
            if (type == null || !type.contains("json")) return null;

            StringBuilder sb = new StringBuilder();
            BufferedReader r = new BufferedReader(new InputStreamReader(co.getInputStream(), "UTF-8"));
            String ligne;
            while ((ligne = r.readLine()) != null) sb.append(ligne);
            r.close();
            return new JSONObject(sb.toString());
        } catch (Throwable t) {
            return null;
        } finally {
            if (co != null) co.disconnect();
        }
    }

    private static void appliquerCertificatChantier(HttpsURLConnection co) throws Exception {
        TrustManager[] tout = new TrustManager[]{ new X509TrustManager() {
            @Override public void checkClientTrusted(X509Certificate[] c, String a) { }
            @Override public void checkServerTrusted(X509Certificate[] c, String a) { }
            @Override public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
        }};
        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(null, tout, new java.security.SecureRandom());
        co.setSSLSocketFactory(ctx.getSocketFactory());
        co.setHostnameVerifier(new HostnameVerifier() {
            @Override public boolean verify(String hote, SSLSession session) {
                return adressePrivee(hote);
            }
        });
    }
}
