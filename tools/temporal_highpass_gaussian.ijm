// Create signed 32-bit temporal high-pass TIFF stacks for calcium video 2.
// Formula: high_pass = raw_32bit - GaussianBlur3D(raw_32bit, x=0, y=0, z=sigma_frames)

requires("1.54p");

inputPath = "/home/jibby2k1/CNEL/State Analysis (Fish)/Separable-Gamma-CFAR/Inputs/050126/050126/calcium video 2.tif";
outputRoot = "/home/jibby2k1/CNEL/State Analysis (Fish)/Separable-Gamma-CFAR/Outputs";
outputHighPass = outputRoot + "/HighPass";
outputDir = outputHighPass + "/calcium_video_2";
sigmas = newArray(4, 6, 8);
labels = newArray("04", "06", "08");

File.makeDirectory(outputRoot);
File.makeDirectory(outputHighPass);
File.makeDirectory(outputDir);
setBatchMode(true);

open(inputPath);
run("32-bit");
rename("raw32_calcium_video_2");
rawTitle = getTitle();
getDimensions(width, height, channels, slices, frames);

summary = "";
summary += "input_path=" + inputPath + "\n";
summary += "output_dir=" + outputDir + "\n";
summary += "formula=high_pass = raw_32bit - GaussianBlur3D(raw_32bit, x=0, y=0, z=sigma_frames)\n";
summary += "sigma_frames=4,6,8\n";
summary += "output_dtype=32-bit float signed residual TIFF stack\n";
summary += "width=" + width + "\n";
summary += "height=" + height + "\n";
summary += "channels=" + channels + "\n";
summary += "slices=" + slices + "\n";
summary += "frames=" + frames + "\n";

for (i = 0; i < sigmas.length; i++) {
    sigma = sigmas[i];
    label = labels[i];

    selectWindow(rawTitle);
    run("Duplicate...", "title=baseline_sigma" + label + " duplicate");
    baselineTitle = getTitle();

    run("Gaussian Blur 3D...", "x=0 y=0 z=" + sigma);

    imageCalculator("Subtract create 32-bit stack", rawTitle, baselineTitle);
    resultTitle = getTitle();
    rename("calcium_video_2_hp_gaussian_sigma" + label + "f_float32");

    savePath = outputDir + "/calcium_video_2_hp_gaussian_sigma" + label + "f_float32.tif";
    saveAs("Tiff", savePath);
    summary += "wrote=" + savePath + "\n";

    close();
    selectWindow(baselineTitle);
    close();
}

selectWindow(rawTitle);
close();

File.saveString(summary, outputDir + "/parameters.txt");
setBatchMode(false);
print(summary);
call("java.lang.System.exit", "0");
