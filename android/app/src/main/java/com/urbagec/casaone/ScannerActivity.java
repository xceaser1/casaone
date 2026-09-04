package com.urbagec.casaone;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.media.Image;
import android.os.Bundle;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.util.Size;
import android.view.View;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.ComponentActivity;
import androidx.annotation.NonNull;
import androidx.camera.core.CameraSelector;
import androidx.camera.core.ExperimentalGetImage;
import androidx.camera.core.ImageAnalysis;
import androidx.camera.core.ImageProxy;
import androidx.camera.core.Preview;
import androidx.camera.lifecycle.ProcessCameraProvider;
import androidx.camera.view.PreviewView;
import androidx.core.content.ContextCompat;

import com.google.android.gms.tasks.OnSuccessListener;
import com.google.common.util.concurrent.ListenableFuture;
import com.google.mlkit.vision.barcode.BarcodeScanner;
import com.google.mlkit.vision.barcode.BarcodeScannerOptions;
import com.google.mlkit.vision.barcode.BarcodeScanning;
import com.google.mlkit.vision.barcode.common.Barcode;
import com.google.mlkit.vision.common.InputImage;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Lecture de badge par la camera, en natif.
 *
 * Remplace jsQR dans le WebView : le decodeur embarque de ML Kit lit
 * nettement plus vite, tolere la basse lumiere et les badges abimes, et n'a
 * besoin d'aucun service en ligne.
 *
 * L'activite se ferme des qu'un badge est lu et renvoie son texte ; la page
 * web garde toute la logique metier (sens du pointage, file d'attente,
 * affichage). Le natif ne fait que decoder.
 */
public class ScannerActivity extends ComponentActivity {

    private static final int REQ_CAM = 11;

    private ExecutorService fil;
    private BarcodeScanner lecteur;
    private PreviewView apercu;
    private boolean rendu = false;   // evite de renvoyer deux fois le meme badge

    @Override
    protected void onCreate(Bundle etat) {
        super.onCreate(etat);
        setContentView(R.layout.scanner);
        apercu = findViewById(R.id.apercu);

        View fermer = findViewById(R.id.fermer);
        if (fermer != null) {
            fermer.setOnClickListener(new View.OnClickListener() {
                @Override public void onClick(View v) { setResult(RESULT_CANCELED); finish(); }
            });
        }

        fil = Executors.newSingleThreadExecutor();
        lecteur = BarcodeScanning.getClient(new BarcodeScannerOptions.Builder()
            .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
            .build());

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.CAMERA}, REQ_CAM);
        } else {
            demarrerCamera();
        }
    }

    @Override
    public void onRequestPermissionsResult(int code, @NonNull String[] permissions,
                                           @NonNull int[] resultats) {
        super.onRequestPermissionsResult(code, permissions, resultats);
        if (code == REQ_CAM) {
            if (resultats.length > 0 && resultats[0] == PackageManager.PERMISSION_GRANTED) {
                demarrerCamera();
            } else {
                Toast.makeText(this, "Accès caméra refusé", Toast.LENGTH_LONG).show();
                setResult(RESULT_CANCELED);
                finish();
            }
        }
    }

    private void demarrerCamera() {
        final ListenableFuture<ProcessCameraProvider> futur =
            ProcessCameraProvider.getInstance(this);
        futur.addListener(new Runnable() {
            @Override public void run() {
                try {
                    ProcessCameraProvider fournisseur = futur.get();

                    Preview preview = new Preview.Builder().build();
                    preview.setSurfaceProvider(apercu.getSurfaceProvider());

                    ImageAnalysis analyse = new ImageAnalysis.Builder()
                        // Une resolution moderee suffit a lire un QR et laisse
                        // la cadence elevee sur les telephones d'entree de gamme.
                        .setTargetResolution(new Size(1280, 720))
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .build();
                    analyse.setAnalyzer(fil, new Analyseur());

                    fournisseur.unbindAll();
                    fournisseur.bindToLifecycle(ScannerActivity.this,
                        CameraSelector.DEFAULT_BACK_CAMERA, preview, analyse);
                } catch (Throwable t) {
                    Toast.makeText(ScannerActivity.this,
                        "Caméra indisponible", Toast.LENGTH_LONG).show();
                    setResult(RESULT_CANCELED);
                    finish();
                }
            }
        }, ContextCompat.getMainExecutor(this));
    }

    private class Analyseur implements ImageAnalysis.Analyzer {
        @Override
        @ExperimentalGetImage
        public void analyze(@NonNull final ImageProxy proxy) {
            Image brute = proxy.getImage();
            if (brute == null || rendu) {
                proxy.close();
                return;
            }
            InputImage image = InputImage.fromMediaImage(
                brute, proxy.getImageInfo().getRotationDegrees());
            lecteur.process(image)
                .addOnSuccessListener(new OnSuccessListener<List<Barcode>>() {
                    @Override public void onSuccess(List<Barcode> codes) {
                        if (!rendu && codes != null && !codes.isEmpty()) {
                            String texte = codes.get(0).getRawValue();
                            if (texte != null && !texte.isEmpty()) rendre(texte);
                        }
                    }
                })
                .addOnCompleteListener(t -> proxy.close());
        }
    }

    private void rendre(String texte) {
        rendu = true;
        vibrer();
        Intent retour = new Intent();
        retour.putExtra("texte", texte);
        setResult(RESULT_OK, retour);
        finish();
    }

    private void vibrer() {
        try {
            Vibrator v = (Vibrator) getSystemService(VIBRATOR_SERVICE);
            if (v != null && v.hasVibrator()) {
                v.vibrate(VibrationEffect.createOneShot(55, VibrationEffect.DEFAULT_AMPLITUDE));
            }
        } catch (Throwable ignore) { }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (fil != null) fil.shutdown();
        if (lecteur != null) lecteur.close();
    }
}
