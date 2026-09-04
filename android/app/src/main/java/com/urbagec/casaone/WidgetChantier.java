package com.urbagec.casaone;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

import org.json.JSONObject;

/**
 * Tuile d'ecran d'accueil : avancement du chantier et presents du jour.
 *
 * Elle n'interroge pas le serveur elle-meme. C'est la veille periodique
 * (Veille) qui lui transmet l'etat deja recupere : une seule requete sert la
 * notification et la tuile, au lieu de deux reveils reseau separes.
 */
public class WidgetChantier extends AppWidgetProvider {

    private static final String PREFS = "widget";

    @Override
    public void onUpdate(Context c, AppWidgetManager gestionnaire, int[] ids) {
        // Redessine avec la derniere valeur connue, puis demande une veille.
        for (int id : ids) {
            gestionnaire.updateAppWidget(id, dessiner(c));
        }
        Veille.programmer(c);
    }

    /** Appele par la veille quand un nouvel etat est disponible. */
    static void rafraichir(Context c, JSONObject etat) {
        try {
            c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString("projet", etat.optString("projet", "CASA ONE"))
                .putString("avancement", etat.isNull("avancement")
                    ? "—" : String.format("%.1f %%", etat.optDouble("avancement", 0)))
                .putString("presents", etat.isNull("presents")
                    ? "—" : String.valueOf(etat.optInt("presents", 0)))
                .apply();

            AppWidgetManager gestionnaire = AppWidgetManager.getInstance(c);
            int[] ids = gestionnaire.getAppWidgetIds(new ComponentName(c, WidgetChantier.class));
            for (int id : ids) {
                gestionnaire.updateAppWidget(id, dessiner(c));
            }
        } catch (Throwable ignore) {
            // Une tuile qui ne se rafraichit pas ne doit pas faire echouer la veille.
        }
    }

    private static RemoteViews dessiner(Context c) {
        RemoteViews vues = new RemoteViews(c.getPackageName(), R.layout.widget_chantier);
        android.content.SharedPreferences p =
            c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);

        vues.setTextViewText(R.id.w_projet, p.getString("projet", "CASA ONE"));
        vues.setTextViewText(R.id.w_avancement, p.getString("avancement", "—"));
        vues.setTextViewText(R.id.w_presents, p.getString("presents", "—"));

        Intent ouvrir = new Intent(c, MainActivity.class);
        ouvrir.putExtra("chemin", "/dashboard");
        ouvrir.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        vues.setOnClickPendingIntent(R.id.w_racine, PendingIntent.getActivity(
            c, 0, ouvrir, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));

        return vues;
    }
}
