package com.urbagec.casaone;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;

/**
 * Miroir natif de la file d'attente des pointages.
 *
 * POURQUOI CE DOUBLON. La page web garde deja ses pointages hors ligne dans
 * IndexedDB, et les envoie des que le reseau revient. Mais cette file ne se
 * vide QUE si la page est ouverte : Background Sync n'existe pas dans une
 * WebView Android. Un chef qui scanne quarante badges dans un sous-sol puis
 * ferme l'application ne verrait rien partir avant sa prochaine ouverture —
 * parfois le lendemain.
 *
 * Le natif tient donc une copie de ce qui est en attente, et WorkManager la
 * vide en tache de fond, application fermee.
 *
 * POURQUOI LE DOUBLE ENVOI EST SANS DANGER. Les deux files peuvent poster le
 * meme pointage : la page au moment ou l'utilisateur la rouvre, la tache de
 * fond quelques minutes plus tot. Le serveur est idempotent par construction —
 * la table des presences porte une contrainte unique (projet, jour, matricule,
 * nom, type). Un second envoi met a jour la meme ligne au lieu d'en creer une
 * seconde. C'est cette garantie, deja en place, qui rend ce miroir acceptable ;
 * sans elle il faudrait un protocole d'accuse de reception entre les deux
 * files, pour un gain nul.
 *
 * La page reste la source de verite : c'est elle qui dit ce qu'elle empile et
 * ce que le serveur a accepte. Si elle oublie de le dire, le pire qui puisse
 * arriver est un envoi en trop.
 */
final class FileNative {

    private static final String FICHIER = "pointages-en-attente.json";
    private static final Object VERROU = new Object();

    /** Au-dela, on ecarte les plus anciens : un fichier qui grossit sans fin
     *  finirait par ralentir chaque ecriture. Mille pointages representent
     *  plusieurs semaines de chantier sans reseau. */
    private static final int MAX = 1000;

    private FileNative() { }

    private static File fichier(Context c) {
        return new File(c.getFilesDir(), FICHIER);
    }

    static JSONArray tous(Context c) {
        synchronized (VERROU) {
            return lire(c);
        }
    }

    static int compter(Context c) {
        return tous(c).length();
    }

    /** Ajoute une ligne. Un uuid deja present n'est jamais duplique. */
    static void enfiler(Context c, JSONObject ligne) {
        if (ligne == null) return;
        String uuid = ligne.optString("uuid", null);
        if (uuid == null || uuid.isEmpty()) return;

        synchronized (VERROU) {
            JSONArray actuel = lire(c);
            for (int i = 0; i < actuel.length(); i++) {
                JSONObject o = actuel.optJSONObject(i);
                if (o != null && uuid.equals(o.optString("uuid"))) return;
            }
            actuel.put(ligne);
            while (actuel.length() > MAX) actuel.remove(0);
            ecrire(c, actuel);
        }
    }

    /** Retire les lignes dont l'uuid est cite. */
    static void retirer(Context c, JSONArray uuids) {
        if (uuids == null || uuids.length() == 0) return;
        synchronized (VERROU) {
            JSONArray actuel = lire(c);
            JSONArray garde = new JSONArray();
            for (int i = 0; i < actuel.length(); i++) {
                JSONObject o = actuel.optJSONObject(i);
                if (o == null) continue;
                String uuid = o.optString("uuid");
                boolean aRetirer = false;
                for (int j = 0; j < uuids.length(); j++) {
                    if (uuid.equals(uuids.optString(j))) { aRetirer = true; break; }
                }
                if (!aRetirer) garde.put(o);
            }
            ecrire(c, garde);
        }
    }

    // ------------------------------------------------------------- disque

    private static JSONArray lire(Context c) {
        File f = fichier(c);
        if (!f.exists()) return new JSONArray();
        InputStream in = null;
        try {
            in = new java.io.FileInputStream(f);
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] tampon = new byte[4096];
            int lu;
            while ((lu = in.read(tampon)) > 0) out.write(tampon, 0, lu);
            return new JSONArray(out.toString("UTF-8"));
        } catch (Throwable t) {
            // Fichier illisible ou corrompu : mieux vaut repartir d'une file
            // vide que de faire planter le scanner a chaque badge.
            return new JSONArray();
        } finally {
            if (in != null) try { in.close(); } catch (Throwable ignore) { }
        }
    }

    private static void ecrire(Context c, JSONArray valeur) {
        // Ecriture par fichier temporaire puis renommage : une coupure de
        // courant au mauvais moment ne doit pas laisser un JSON tronque, qui
        // emporterait toute la file au lieu d'un seul pointage.
        File cible = fichier(c);
        File temporaire = new File(c.getFilesDir(), FICHIER + ".tmp");
        FileOutputStream out = null;
        try {
            out = new FileOutputStream(temporaire);
            out.write(valeur.toString().getBytes("UTF-8"));
            out.flush();
            out.getFD().sync();
            out.close();
            out = null;
            if (cible.exists() && !cible.delete()) return;
            if (!temporaire.renameTo(cible)) temporaire.delete();
        } catch (Throwable ignore) {
            // Une file qu'on n'arrive pas a ecrire ne doit jamais faire tomber
            // l'application : la page garde de toute facon sa propre copie.
        } finally {
            if (out != null) try { out.close(); } catch (Throwable ignore) { }
        }
    }
}
