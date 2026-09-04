package com.urbagec.casaone;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.content.Intent;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;

import org.json.JSONObject;

/**
 * Controle de version au demarrage.
 *
 * Le serveur annonce la version publiee (APK_VERSION_CODE) ; l'application
 * compare avec la sienne et propose le telechargement. Cela evite d'avoir a
 * rediffuser un fichier APK a la main et de laisser des telephones sur une
 * version ancienne sans le savoir.
 *
 * Aucune installation forcee : on informe, l'utilisateur decide. La proposition
 * n'est faite qu'une fois par version pour ne pas devenir agacante.
 */
final class VerificationVersion {

    private static final String PREFS = "maj";

    private VerificationVersion() { }

    static void lancer(final Activity activite) {
        new Thread(new Runnable() {
            @Override public void run() {
                final JSONObject info = Reseau.json(activite, "/api/mobile/version");
                if (info == null) return;

                final int publiee = info.optInt("version_code", 0);
                final String url = info.optString("url", "");
                if (publiee <= BuildConfig.VERSION_CODE || url.isEmpty()) return;

                // Une seule proposition par version publiee.
                if (activite.getSharedPreferences(PREFS, Activity.MODE_PRIVATE)
                        .getInt("refusee", 0) == publiee) {
                    return;
                }

                new Handler(Looper.getMainLooper()).post(new Runnable() {
                    @Override public void run() { proposer(activite, info, publiee, url); }
                });
            }
        }).start();
    }

    private static void proposer(final Activity activite, JSONObject info,
                                 final int publiee, final String url) {
        if (activite.isFinishing()) return;
        String notes = info.optString("notes", "");
        String message = "Version " + info.optString("version_nom", String.valueOf(publiee))
            + " disponible." + (notes.isEmpty() ? "" : "\n\n" + notes);

        new AlertDialog.Builder(activite)
            .setTitle("Mise à jour")
            .setMessage(message)
            .setPositiveButton("Télécharger", new DialogInterface.OnClickListener() {
                @Override public void onClick(DialogInterface d, int w) {
                    try {
                        activite.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                    } catch (Throwable ignore) { }
                }
            })
            .setNegativeButton("Plus tard", new DialogInterface.OnClickListener() {
                @Override public void onClick(DialogInterface d, int w) {
                    activite.getSharedPreferences(PREFS, Activity.MODE_PRIVATE)
                        .edit().putInt("refusee", publiee).apply();
                }
            })
            .show();
    }
}
