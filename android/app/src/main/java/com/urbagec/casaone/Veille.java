package com.urbagec.casaone;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import androidx.annotation.NonNull;
import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

import org.json.JSONObject;

import java.util.concurrent.TimeUnit;

/**
 * Veille periodique : interroge le serveur en tache de fond et notifie.
 *
 * CHOIX D'ARCHITECTURE — pourquoi pas de vraies notifications poussees :
 * Firebase Cloud Messaging exigerait de creer un projet Google, d'embarquer
 * google-services.json et de faire dependre le chantier d'un service tiers.
 * Une verification periodique interroge directement VOTRE serveur, ne demande
 * aucun compte, et suffit largement : un stock sous le seuil ou un plan a
 * valider ne se joue pas a la minute. Le prix a payer est la latence — Android
 * n'autorise pas mieux que 15 minutes, et espace davantage si la batterie est
 * faible.
 *
 * La tuile de l'ecran d'accueil est rafraichie au passage : une seule requete
 * sert les deux besoins.
 */
public class Veille extends Worker {

    private static final String TACHE = "casaone-veille";
    private static final String CANAL = "casaone-chantier";
    private static final String PREFS_VU = "veille";

    public Veille(@NonNull Context c, @NonNull WorkerParameters p) {
        super(c, p);
    }

    /** Programme la verification. Idempotent : appelable a chaque demarrage. */
    static void programmer(Context c) {
        try {
            Constraints contraintes = new Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build();
            PeriodicWorkRequest demande = new PeriodicWorkRequest.Builder(
                    Veille.class, 30, TimeUnit.MINUTES)
                .setConstraints(contraintes)
                .build();
            WorkManager.getInstance(c).enqueueUniquePeriodicWork(
                TACHE, ExistingPeriodicWorkPolicy.KEEP, demande);
        } catch (Throwable ignore) {
            // Une veille qui ne demarre pas ne doit jamais empecher l'application
            // de s'ouvrir.
        }
    }

    @NonNull
    @Override
    public Result doWork() {
        JSONObject etat = Reseau.json(getApplicationContext(), "/api/mobile/etat");
        if (etat == null || !etat.optBoolean("ok", false)) {
            // Hors ligne ou session expiree : on reessaiera au prochain tour.
            return Result.success();
        }

        WidgetChantier.rafraichir(getApplicationContext(), etat);
        signaler(etat);
        return Result.success();
    }

    /**
     * Notifie uniquement ce qui a CHANGE depuis la derniere verification.
     *
     * Renotifier le meme chiffre toutes les 30 minutes ferait desinstaller
     * l'application en une journee.
     */
    private void signaler(JSONObject etat) {
        Context c = getApplicationContext();
        SharedPreferences vu = c.getSharedPreferences(PREFS_VU, Context.MODE_PRIVATE);

        int alertes = etat.optInt("alertes_stock", 0);
        int plans = etat.optInt("plans_en_attente", 0);

        if (alertes > 0 && alertes != vu.getInt("alertes", 0)) {
            notifier(c, 1, "Stock sous le seuil",
                alertes + (alertes > 1 ? " articles à réapprovisionner" : " article à réapprovisionner"),
                "/stock/");
        }
        if (plans > 0 && plans != vu.getInt("plans", 0)) {
            notifier(c, 2, "Plans à valider",
                plans + (plans > 1 ? " plans en attente" : " plan en attente"),
                "/validation");
        }

        vu.edit().putInt("alertes", alertes).putInt("plans", plans).apply();
    }

    private void notifier(Context c, int id, String titre, String texte, String chemin) {
        NotificationManager nm =
            (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;

        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel canal = new NotificationChannel(
                CANAL, "Suivi du chantier", NotificationManager.IMPORTANCE_DEFAULT);
            canal.setDescription("Stock, plans à valider et pointages");
            nm.createNotificationChannel(canal);
        }

        Intent ouvrir = new Intent(c, MainActivity.class);
        ouvrir.putExtra("chemin", chemin);
        ouvrir.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent action = PendingIntent.getActivity(
            c, id, ouvrir, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        android.app.Notification.Builder b = Build.VERSION.SDK_INT >= 26
            ? new android.app.Notification.Builder(c, CANAL)
            : new android.app.Notification.Builder(c);

        nm.notify(id, b.setContentTitle(titre)
            .setContentText(texte)
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setAutoCancel(true)
            .setContentIntent(action)
            .build());
    }
}
