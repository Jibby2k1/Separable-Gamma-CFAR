// Interactive neuron-first review app for calcium_video_2.
//
// This script builds stable candidate neuron footprints from an aggregate
// robust-z projection, extracts raw and local-background-corrected traces,
// applies an event-preserving trace-level Kalman baseline estimate, and writes
// a static HTML app with frame scrubbing, ROI overlays, trace plots, and
// accept/reject review export.

import ij.IJ
import ij.ImagePlus
import java.awt.BasicStroke
import java.awt.Color
import java.awt.Font
import java.awt.RenderingHints
import java.awt.image.BufferedImage
import javax.imageio.ImageIO
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.util.ArrayDeque
import java.util.Arrays

final Path projectRoot = Paths.get("/home/jibby2k1/CNEL/State Analysis (Fish)/Separable-Gamma-CFAR")
final Path rawPath = projectRoot.resolve("Inputs/050126/050126/calcium video 2.tif")
final Path zPath = projectRoot.resolve("Outputs/CandidateEventPipeline/calcium_video_2/calcium_video_2_sigma06_robust_positive_z_float32.tif")
final Path outputDir = projectRoot.resolve("Outputs/NeuronReview/calcium_video_2/app")
final Path frameDir = outputDir.resolve("frames")
final Path evidenceDir = outputDir.resolve("evidence")

final int minRoiArea = 8
final int maxRoiArea = 260
final int maxRois = 90
final int nonMaxRadius = 4
final int minPeakDistance = 9
final int footprintRadius = 9
final int backgroundOuterRadius = 15
final double zActiveThreshold = 2.0d
final double eventZThreshold = 2.4d
final double neuropilWeight = 0.7d
final double kalmanGain = 0.060d
final double kalmanSpikeGain = 0.008d
final double kalmanNegativeGain = 0.110d

Files.createDirectories(frameDir)
Files.createDirectories(evidenceDir)

static float[] pixelsAsFloat(ImagePlus imp, int frame) {
    return (float[]) imp.getStack().getProcessor(frame).convertToFloatProcessor().getPixels()
}

static double percentile(float[] values, double fraction) {
    float[] copy = values.clone()
    Arrays.sort(copy)
    int idx = Math.max(0, Math.min(copy.length - 1, Math.round((copy.length - 1) * fraction) as int))
    return copy[idx] as double
}

static double percentile(double[] values, double fraction) {
    double[] copy = values.clone()
    Arrays.sort(copy)
    int idx = Math.max(0, Math.min(copy.length - 1, Math.round((copy.length - 1) * fraction) as int))
    return copy[idx]
}

static double median(double[] values) {
    return percentile(values, 0.5d)
}

static double madSigma(double[] values, double center) {
    double[] dev = new double[values.length]
    for (int i = 0; i < values.length; i++) dev[i] = Math.abs(values[i] - center)
    return Math.max(1.0e-6d, 1.4826d * median(dev))
}

static int clampByte(double value) {
    if (value < 0.0d) return 0
    if (value > 255.0d) return 255
    return Math.round(value) as int
}

static float[] boxSmooth3x3(float[] src, int width, int height) {
    float[] dst = new float[src.length]
    for (int y = 0; y < height; y++) {
        int y0 = Math.max(0, y - 1)
        int y1 = Math.min(height - 1, y + 1)
        for (int x = 0; x < width; x++) {
            int x0 = Math.max(0, x - 1)
            int x1 = Math.min(width - 1, x + 1)
            double sum = 0.0d
            int count = 0
            for (int yy = y0; yy <= y1; yy++) {
                int row = yy * width
                for (int xx = x0; xx <= x1; xx++) {
                    sum += src[row + xx] as double
                    count++
                }
            }
            dst[y * width + x] = (float) (sum / count)
        }
    }
    return dst
}

static boolean isLocalMax(float[] score, int width, int height, int x, int y, int radius) {
    double center = score[y * width + x] as double
    for (int yy = Math.max(0, y - radius); yy <= Math.min(height - 1, y + radius); yy++) {
        int row = yy * width
        for (int xx = Math.max(0, x - radius); xx <= Math.min(width - 1, x + radius); xx++) {
            if (xx == x && yy == y) continue
            if ((score[row + xx] as double) > center) return false
        }
    }
    return true
}

static List<Integer> growFootprint(float[] score, boolean[] assigned, int width, int height, int seedIdx, double threshold, int maxRadius) {
    int seedY = seedIdx.intdiv(width)
    int seedX = seedIdx - seedY * width
    boolean[] visited = new boolean[score.length]
    ArrayDeque<Integer> queue = new ArrayDeque<>()
    List<Integer> pixels = []
    queue.add(seedIdx)
    visited[seedIdx] = true
    int[] dx = [-1, 0, 1, -1, 1, -1, 0, 1] as int[]
    int[] dy = [-1, -1, -1, 0, 0, 1, 1, 1] as int[]
    int r2 = maxRadius * maxRadius
    while (!queue.isEmpty()) {
        int idx = queue.removeFirst()
        if (assigned[idx]) continue
        int y = idx.intdiv(width)
        int x = idx - y * width
        int ddx = x - seedX
        int ddy = y - seedY
        if (ddx * ddx + ddy * ddy > r2) continue
        if ((score[idx] as double) < threshold) continue
        pixels.add(idx)
        for (int k = 0; k < 8; k++) {
            int nx = x + dx[k]
            int ny = y + dy[k]
            if (nx < 0 || nx >= width || ny < 0 || ny >= height) continue
            int nidx = ny * width + nx
            if (!visited[nidx]) {
                visited[nidx] = true
                queue.add(nidx)
            }
        }
    }
    return pixels
}

static int[] ringPixels(List<Integer> roiPixels, boolean[] anyRoi, int width, int height, int outerRadius) {
    boolean[] roi = new boolean[width * height]
    int minX = width
    int minY = height
    int maxX = -1
    int maxY = -1
    roiPixels.each { idx ->
        roi[idx] = true
        int y = idx.intdiv(width)
        int x = idx - y * width
        if (x < minX) minX = x
        if (x > maxX) maxX = x
        if (y < minY) minY = y
        if (y > maxY) maxY = y
    }
    Set<Integer> ring = new LinkedHashSet<>()
    int expand = outerRadius
    for (int y = Math.max(0, minY - expand); y <= Math.min(height - 1, maxY + expand); y++) {
        int row = y * width
        for (int x = Math.max(0, minX - expand); x <= Math.min(width - 1, maxX + expand); x++) {
            int idx = row + x
            if (roi[idx] || anyRoi[idx]) continue
            boolean near = false
            roiPixels.each { ridx ->
                if (near) return
                int ry = ridx.intdiv(width)
                int rx = ridx - ry * width
                int dx = x - rx
                int dy = y - ry
                if (dx * dx + dy * dy <= outerRadius * outerRadius) near = true
            }
            if (near) ring.add(idx)
        }
    }
    return ring.collect { it as int } as int[]
}

static double[] meanTrace(float[][] frames, List<Integer> pixels) {
    int tCount = frames.length
    double[] trace = new double[tCount]
    if (pixels.isEmpty()) return trace
    for (int t = 0; t < tCount; t++) {
        double sum = 0.0d
        float[] frame = frames[t]
        pixels.each { idx -> sum += frame[idx] as double }
        trace[t] = sum / pixels.size()
    }
    return trace
}

static double[] meanTrace(float[][] frames, int[] pixels, double[] fallback) {
    int tCount = frames.length
    double[] trace = new double[tCount]
    if (pixels.length == 0) return fallback.clone()
    for (int t = 0; t < tCount; t++) {
        double sum = 0.0d
        float[] frame = frames[t]
        for (int i = 0; i < pixels.length; i++) sum += frame[pixels[i]] as double
        trace[t] = sum / pixels.length
    }
    return trace
}

static Map<String, Object> traceModel(double[] rawTrace, double[] bgTrace, double neuropilWeight, double gain, double spikeGain, double negativeGain, double eventThreshold) {
    int n = rawTrace.length
    double[] corrected = new double[n]
    for (int i = 0; i < n; i++) corrected[i] = rawTrace[i] - neuropilWeight * bgTrace[i]
    double base0 = percentile(corrected, 0.20d)
    double scaleBase = Math.max(1.0d, Math.abs(base0))
    double[] dff = new double[n]
    for (int i = 0; i < n; i++) dff[i] = (corrected[i] - base0) / scaleBase
    double center = median(dff)
    double sigma = madSigma(dff, center)
    double baseline = center
    double[] baselineTrace = new double[n]
    double[] eventTrace = new double[n]
    double[] zTrace = new double[n]
    for (int i = 0; i < n; i++) {
        double residual = dff[i] - baseline
        double k = gain
        if (residual > 2.5d * sigma) k = spikeGain
        if (residual < -1.0d * sigma) k = negativeGain
        baseline += k * residual
        baselineTrace[i] = baseline
        double innovation = dff[i] - baseline
        eventTrace[i] = Math.max(0.0d, innovation)
        zTrace[i] = eventTrace[i] / Math.max(1.0e-6d, sigma)
    }
    List<Map<String, Object>> events = []
    int lastEvent = -99
    for (int i = 1; i < n - 1; i++) {
        if (zTrace[i] >= eventThreshold && zTrace[i] >= zTrace[i - 1] && zTrace[i] >= zTrace[i + 1] && i - lastEvent >= 2) {
            events.add([frame: i + 1, z: zTrace[i], amplitude: eventTrace[i]])
            lastEvent = i
        }
    }
    return [
        corrected: corrected,
        dff: dff,
        baseline: baselineTrace,
        eventTrace: eventTrace,
        zTrace: zTrace,
        noiseSigma: sigma,
        events: events
    ]
}

static List<Double> rounded(double[] values, int places) {
    double scale = Math.pow(10.0d, places)
    List<Double> out = new ArrayList<>(values.length)
    for (int i = 0; i < values.length; i++) out.add(Math.round(values[i] * scale) / scale)
    return out
}

static Object jsonValue(Object value) {
    if (value == null) return "null"
    if (value instanceof Number || value instanceof Boolean) return value.toString()
    if (value instanceof Map) {
        return "{" + value.collect { k, v -> jsonValue(k.toString()) + ":" + jsonValue(v) }.join(",") + "}"
    }
    if (value instanceof Iterable) {
        return "[" + value.collect { jsonValue(it) }.join(",") + "]"
    }
    String s = value.toString()
    return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "") + "\""
}

static void writePng(float[] pixels, int width, int height, Path path) {
    double lo = percentile(pixels, 0.005d)
    double hi = percentile(pixels, 0.997d)
    double range = Math.max(1.0d, hi - lo)
    BufferedImage img = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB)
    for (int y = 0; y < height; y++) {
        int row = y * width
        for (int x = 0; x < width; x++) {
            int v = clampByte(((pixels[row + x] as double) - lo) * 255.0d / range)
            img.setRGB(x, y, (v << 16) | (v << 8) | v)
        }
    }
    ImageIO.write(img, "png", path.toFile())
}

static float[] normalize01(float[] values) {
    double lo = percentile(values, 0.01d)
    double hi = percentile(values, 0.995d)
    double range = Math.max(1.0e-6d, hi - lo)
    float[] out = new float[values.length]
    for (int i = 0; i < values.length; i++) {
        double v = ((values[i] as double) - lo) / range
        if (v < 0.0d) v = 0.0d
        if (v > 1.0d) v = 1.0d
        out[i] = (float) v
    }
    return out
}

static boolean nearExistingCentroid(List<Map<String, Object>> rois, int x, int y, double minDistance) {
    double minD2 = minDistance * minDistance
    return rois.any { roi ->
        double dx = (roi.centroidX as double) - x
        double dy = (roi.centroidY as double) - y
        return dx * dx + dy * dy < minD2
    }
}

println("Loading raw video: ${rawPath}")
ImagePlus rawImp = IJ.openImage(rawPath.toString())
if (rawImp == null) throw new IllegalStateException("Could not open raw video: ${rawPath}")
ImagePlus zImp = IJ.openImage(zPath.toString())
if (zImp == null) throw new IllegalStateException("Could not open robust z stack: ${zPath}")

final int width = rawImp.getWidth()
final int height = rawImp.getHeight()
final int frames = rawImp.getStackSize()
final int pixelsPerFrame = width * height

println("Reading ${frames} raw frames into memory")
float[][] rawFrames = new float[frames][]
double[] frameMean = new double[frames]
double[] rawSum = new double[pixelsPerFrame]
double[] rawSumSq = new double[pixelsPerFrame]
float[] rawMax = new float[pixelsPerFrame]
for (int f = 1; f <= frames; f++) {
    float[] pix = pixelsAsFloat(rawImp, f)
    rawFrames[f - 1] = pix
    double sum = 0.0d
    for (int i = 0; i < pix.length; i++) {
        double value = pix[i] as double
        sum += value
        rawSum[i] += value
        rawSumSq[i] += value * value
        if (f == 1 || value > (rawMax[i] as double)) rawMax[i] = (float) value
    }
    frameMean[f - 1] = sum / pix.length
    writePng(pix, width, height, frameDir.resolve(String.format("frame_%03d.png", f)))
}

float[] rawMean = new float[pixelsPerFrame]
float[] rawStd = new float[pixelsPerFrame]
for (int i = 0; i < pixelsPerFrame; i++) {
    double mean = rawSum[i] / frames
    double var = Math.max(0.0d, rawSumSq[i] / frames - mean * mean)
    rawMean[i] = (float) mean
    rawStd[i] = (float) Math.sqrt(var)
}

println("Building aggregate robust-z projection from ${zPath.fileName}")
float[] maxZ = new float[pixelsPerFrame]
int[] activeCount = new int[pixelsPerFrame]
for (int f = 1; f <= frames; f++) {
    float[] z = pixelsAsFloat(zImp, f)
    for (int i = 0; i < pixelsPerFrame; i++) {
        double v = z[i] as double
        if (v > (maxZ[i] as double)) maxZ[i] = (float) v
        if (v >= zActiveThreshold) activeCount[i]++
    }
}
float[] score = new float[pixelsPerFrame]
for (int i = 0; i < pixelsPerFrame; i++) {
    double persistence = Math.min(1.0d, activeCount[i] / 10.0d)
    score[i] = (float) ((maxZ[i] as double) * (1.0d + 0.35d * persistence))
}
score = boxSmooth3x3(boxSmooth3x3(score, width, height), width, height)

double peakThreshold = percentile(score, 0.985d)
double growFloor = percentile(score, 0.940d)
println(String.format("ROI projection thresholds: peak >= %.3f, grow floor >= %.3f", peakThreshold, growFloor))

List<Integer> peakCandidates = []
for (int y = nonMaxRadius; y < height - nonMaxRadius; y++) {
    for (int x = nonMaxRadius; x < width - nonMaxRadius; x++) {
        int idx = y * width + x
        if ((score[idx] as double) >= peakThreshold && isLocalMax(score, width, height, x, y, nonMaxRadius)) {
            peakCandidates.add(idx)
        }
    }
}
peakCandidates.sort { a, b -> (score[b] as double) <=> (score[a] as double) }

List<Map<String, Object>> rois = []
boolean[] assigned = new boolean[pixelsPerFrame]
peakCandidates.each { seedIdx ->
    if (rois.size() >= maxRois) return
    int sy = seedIdx.intdiv(width)
    int sx = seedIdx - sy * width
    boolean tooClose = rois.any { roi ->
        double dx = (roi.centroidX as double) - sx
        double dy = (roi.centroidY as double) - sy
        return dx * dx + dy * dy < minPeakDistance * minPeakDistance
    }
    if (tooClose) return
    double seedScore = score[seedIdx] as double
    double growThreshold = Math.max(growFloor, 0.42d * seedScore)
    List<Integer> region = growFootprint(score, assigned, width, height, seedIdx, growThreshold, footprintRadius)
    if (region.size() < minRoiArea || region.size() > maxRoiArea) return
    double sumX = 0.0d
    double sumY = 0.0d
    int minX = width
    int minY = height
    int maxX = -1
    int maxY = -1
    region.each { idx ->
        int y = idx.intdiv(width)
        int x = idx - y * width
        sumX += x
        sumY += y
        if (x < minX) minX = x
        if (x > maxX) maxX = x
        if (y < minY) minY = y
        if (y > maxY) maxY = y
    }
    region.each { assigned[it] = true }
    rois.add([
        id: rois.size() + 1,
        seedX: sx,
        seedY: sy,
        centroidX: sumX / region.size(),
        centroidY: sumY / region.size(),
        area: region.size(),
        peakScore: seedScore,
        minX: minX,
        minY: minY,
        maxX: maxX,
        maxY: maxY,
        pixels: region
    ])
}
println("Detected ${rois.size()} stable candidate ROIs")

boolean[] anyRoi = new boolean[pixelsPerFrame]
rois.each { roi -> (roi.pixels as List<Integer>).each { anyRoi[it] = true } }

println("Writing evidence maps and missed-neuron discovery suggestions")
float[] activeCountFloat = new float[pixelsPerFrame]
float[] uncoveredScore = new float[pixelsPerFrame]
boolean[] blockedByRoi = new boolean[pixelsPerFrame]
rois.each { roi ->
    (roi.pixels as List<Integer>).each { idx ->
        int y = idx.intdiv(width)
        int x = idx - y * width
        for (int yy = Math.max(0, y - minPeakDistance); yy <= Math.min(height - 1, y + minPeakDistance); yy++) {
            int row = yy * width
            for (int xx = Math.max(0, x - minPeakDistance); xx <= Math.min(width - 1, x + minPeakDistance); xx++) {
                int dx = xx - x
                int dy = yy - y
                if (dx * dx + dy * dy <= minPeakDistance * minPeakDistance) {
                    blockedByRoi[row + xx] = true
                }
            }
        }
    }
}
for (int i = 0; i < pixelsPerFrame; i++) {
    activeCountFloat[i] = (float) activeCount[i]
    uncoveredScore[i] = blockedByRoi[i] ? 0.0f : score[i]
}
float[] localContrast = boxSmooth3x3(rawStd, width, height)
float[] nMaxZ = normalize01(maxZ)
float[] nStd = normalize01(rawStd)
float[] nActive = normalize01(activeCountFloat)
float[] nUncovered = normalize01(uncoveredScore)
float[] discoveryScore = new float[pixelsPerFrame]
for (int i = 0; i < pixelsPerFrame; i++) {
    discoveryScore[i] = blockedByRoi[i] ? 0.0f : (float) (
        0.40d * (nMaxZ[i] as double) +
        0.25d * (nStd[i] as double) +
        0.20d * (nActive[i] as double) +
        0.15d * (nUncovered[i] as double)
    )
}
discoveryScore = boxSmooth3x3(discoveryScore, width, height)

writePng(rawMean, width, height, evidenceDir.resolve("mean_projection.png"))
writePng(rawMax, width, height, evidenceDir.resolve("max_projection.png"))
writePng(rawStd, width, height, evidenceDir.resolve("std_projection.png"))
writePng(activeCountFloat, width, height, evidenceDir.resolve("peak_count_z_ge_2.png"))
writePng(maxZ, width, height, evidenceDir.resolve("robust_z_max.png"))
writePng(uncoveredScore, width, height, evidenceDir.resolve("uncovered_robust_z_score.png"))
writePng(localContrast, width, height, evidenceDir.resolve("local_contrast_proxy.png"))
writePng(discoveryScore, width, height, evidenceDir.resolve("discovery_score.png"))

List<Map<String, Object>> discoverySuggestions = []
List<Integer> suggestionPeaks = []
double suggestionThreshold = percentile(discoveryScore, 0.985d)
for (int y = nonMaxRadius; y < height - nonMaxRadius; y++) {
    for (int x = nonMaxRadius; x < width - nonMaxRadius; x++) {
        int idx = y * width + x
        if ((discoveryScore[idx] as double) >= suggestionThreshold &&
            !blockedByRoi[idx] &&
            isLocalMax(discoveryScore, width, height, x, y, nonMaxRadius) &&
            !nearExistingCentroid(rois, x, y, minPeakDistance * 1.5d)) {
            suggestionPeaks.add(idx)
        }
    }
}
suggestionPeaks.sort { a, b -> (discoveryScore[b] as double) <=> (discoveryScore[a] as double) }
boolean[] suggestionAssigned = blockedByRoi.clone()
suggestionPeaks.each { seedIdx ->
    if (discoverySuggestions.size() >= 80) return
    int sy = seedIdx.intdiv(width)
    int sx = seedIdx - sy * width
    boolean tooCloseSuggestion = discoverySuggestions.any { s ->
        double dx = (s.centroidX as double) - sx
        double dy = (s.centroidY as double) - sy
        return dx * dx + dy * dy < minPeakDistance * minPeakDistance
    }
    if (tooCloseSuggestion) return
    double seedScore = discoveryScore[seedIdx] as double
    List<Integer> region = growFootprint(discoveryScore, suggestionAssigned, width, height, seedIdx, Math.max(0.18d, 0.38d * seedScore), footprintRadius)
    if (region.size() < minRoiArea || region.size() > maxRoiArea) return
    double sumX = 0.0d
    double sumY = 0.0d
    int minX = width
    int minY = height
    int maxX = -1
    int maxY = -1
    double maxRaw = 0.0d
    region.each { idx ->
        suggestionAssigned[idx] = true
        int y = idx.intdiv(width)
        int x = idx - y * width
        sumX += x
        sumY += y
        if (x < minX) minX = x
        if (x > maxX) maxX = x
        if (y < minY) minY = y
        if (y > maxY) maxY = y
        if ((rawMax[idx] as double) > maxRaw) maxRaw = rawMax[idx] as double
    }
    int bboxW = maxX - minX + 1
    int bboxH = maxY - minY + 1
    double aspect = Math.max(bboxW, bboxH) / Math.max(1.0d, Math.min(bboxW, bboxH) as double)
    String artifactCue = "none"
    if (minX <= 1 || minY <= 1 || maxX >= width - 2 || maxY >= height - 2) artifactCue = "border"
    else if (aspect > 4.0d) artifactCue = "elongated_structure"
    else if (maxRaw >= percentile(rawMax, 0.998d)) artifactCue = "very_bright"
    discoverySuggestions.add([
        id: "S" + (discoverySuggestions.size() + 1),
        provenance: "uncovered_combined",
        centroidX: Math.round((sumX / region.size()) * 10.0d) / 10.0d,
        centroidY: Math.round((sumY / region.size()) * 10.0d) / 10.0d,
        area: region.size(),
        discoveryScore: Math.round(seedScore * 1000.0d) / 1000.0d,
        maxZ: Math.round((maxZ[seedIdx] as double) * 100.0d) / 100.0d,
        activeFrames: activeCount[seedIdx],
        bbox: [minX, minY, maxX, maxY],
        artifactCue: artifactCue,
        points: region.collect { idx ->
            int y = idx.intdiv(width)
            int x = idx - y * width
            [x, y]
        }
    ])
}
Files.write(outputDir.resolve("discovery_suggestions.tsv"), ("suggestion_id\tcentroid_x\tcentroid_y\tarea\tdiscovery_score\tmax_z\tactive_frames\tartifact_cue\n" +
    discoverySuggestions.collect { s -> "${s.id}\t${s.centroidX}\t${s.centroidY}\t${s.area}\t${s.discoveryScore}\t${s.maxZ}\t${s.activeFrames}\t${s.artifactCue}" }.join("\n") + "\n").getBytes("UTF-8"))

println("Extracting ROI traces and trace-level Kalman event scores")
List<Map<String, Object>> roiJson = []
rois.each { roi ->
    List<Integer> roiPixels = roi.pixels as List<Integer>
    int[] bgPixels = ringPixels(roiPixels, anyRoi, width, height, backgroundOuterRadius)
    double[] rawTrace = meanTrace(rawFrames, roiPixels)
    double[] bgTrace = meanTrace(rawFrames, bgPixels, frameMean)
    Map<String, Object> model = traceModel(rawTrace, bgTrace, neuropilWeight, kalmanGain, kalmanSpikeGain, kalmanNegativeGain, eventZThreshold)
    List<List<Integer>> pointPairs = roiPixels.collect { idx ->
        int y = idx.intdiv(width)
        int x = idx - y * width
        [x, y]
    }
    roiJson.add([
        id: roi.id,
        centroidX: Math.round((roi.centroidX as double) * 10.0d) / 10.0d,
        centroidY: Math.round((roi.centroidY as double) * 10.0d) / 10.0d,
        area: roi.area,
        peakScore: Math.round((roi.peakScore as double) * 100.0d) / 100.0d,
        bbox: [roi.minX, roi.minY, roi.maxX, roi.maxY],
        points: pointPairs,
        rawTrace: rounded(rawTrace, 2),
        backgroundTrace: rounded(bgTrace, 2),
        dffTrace: rounded(model.dff as double[], 5),
        baselineTrace: rounded(model.baseline as double[], 5),
        eventTrace: rounded(model.eventTrace as double[], 5),
        zTrace: rounded(model.zTrace as double[], 3),
        noiseSigma: Math.round((model.noiseSigma as double) * 100000.0d) / 100000.0d,
        events: (model.events as List<Map<String, Object>>).collect { e ->
            [frame: e.frame, z: Math.round((e.z as double) * 100.0d) / 100.0d, amplitude: Math.round((e.amplitude as double) * 100000.0d) / 100000.0d]
        }
    ])
}

Map<String, Object> reviewData = [
    video: [
        name: "calcium video 2.tif",
        width: width,
        height: height,
        frames: frames,
        framePattern: "frames/frame_%03d.png"
    ],
    discovery: [
        evidenceMaps: [
            [id: "raw_mean", label: "Raw mean", file: "evidence/mean_projection.png"],
            [id: "raw_max", label: "Raw max", file: "evidence/max_projection.png"],
            [id: "raw_std", label: "Raw std", file: "evidence/std_projection.png"],
            [id: "peak_count", label: "Peak count z>=2", file: "evidence/peak_count_z_ge_2.png"],
            [id: "robust_z_max", label: "Robust z max", file: "evidence/robust_z_max.png"],
            [id: "uncovered", label: "Uncovered robust-z score", file: "evidence/uncovered_robust_z_score.png"],
            [id: "local_contrast", label: "Local contrast proxy", file: "evidence/local_contrast_proxy.png"],
            [id: "discovery_score", label: "Discovery score", file: "evidence/discovery_score.png"],
        ],
        suggestions: discoverySuggestions
    ],
    parameters: [
        sourceZStack: zPath.toString(),
        minRoiArea: minRoiArea,
        maxRoiArea: maxRoiArea,
        maxRois: maxRois,
        peakThreshold: Math.round(peakThreshold * 1000.0d) / 1000.0d,
        growFloor: Math.round(growFloor * 1000.0d) / 1000.0d,
        eventZThreshold: eventZThreshold,
        neuropilWeight: neuropilWeight,
        kalmanGain: kalmanGain,
        kalmanSpikeGain: kalmanSpikeGain,
        kalmanNegativeGain: kalmanNegativeGain
    ],
    rois: roiJson
]

String dataJson = jsonValue(reviewData).toString()
Files.write(outputDir.resolve("review_data.json"), dataJson.getBytes("UTF-8"))
Files.write(outputDir.resolve("roi_summary.tsv"), ("roi_id\tcentroid_x\tcentroid_y\tarea\tpeak_score\tevent_count\tnoise_sigma\n" +
    roiJson.collect { roi -> "${roi.id}\t${roi.centroidX}\t${roi.centroidY}\t${roi.area}\t${roi.peakScore}\t${(roi.events as List).size()}\t${roi.noiseSigma}" }.join("\n") + "\n").getBytes("UTF-8"))
Files.write(outputDir.resolve("parameters.txt"), [
    "raw_video=${rawPath}",
    "source_z_stack=${zPath}",
    "output_dir=${outputDir}",
    "roi_count=${roiJson.size()}",
    "discovery_suggestion_count=${discoverySuggestions.size()}",
    "frame_count=${frames}",
    "event_z_threshold=${eventZThreshold}",
    "denoising=trace_level_robust_kalman_baseline",
    "kalman_gain=${kalmanGain}",
    "kalman_spike_gain=${kalmanSpikeGain}",
    "kalman_negative_gain=${kalmanNegativeGain}",
    "neuropil_weight=${neuropilWeight}"
].join("\n").getBytes("UTF-8"))

String html = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Neuron Review - calcium_video_2</title>
<style>
:root{color-scheme:light;--bg:#f7f8fb;--panel:#fff;--ink:#111827;--muted:#64748b;--line:#d9e0ea;--accent:#0ea5e9;--event:#facc15;--ok:#16a34a;--bad:#dc2626;--unsure:#9333ea}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:Arial,Helvetica,sans-serif}.app{display:grid;grid-template-columns:minmax(620px,1fr) 430px;height:100vh;gap:0}.stage{padding:14px 16px 16px;min-width:0}.side{border-left:1px solid var(--line);background:var(--panel);padding:14px;overflow:auto}h1{font-size:18px;margin:0 0 8px}h2{font-size:15px;margin:16px 0 8px}.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px}.toolbar button,.toolbar select{height:30px;border:1px solid var(--line);background:white;border-radius:6px;padding:0 10px}.toolbar label{font-size:13px;color:var(--muted)}input[type=range]{vertical-align:middle}.viewerWrap{position:relative;display:inline-block;background:#0b1220;border:1px solid #cbd5e1;max-width:100%}#frameImg{display:block;width:min(100%,900px);height:auto;image-rendering:auto}#overlay{position:absolute;left:0;top:0;width:100%;height:100%;cursor:crosshair}.status{font-size:13px;color:var(--muted);margin-top:8px}.metricGrid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.metric{border:1px solid var(--line);border-radius:7px;padding:8px;background:#f8fafc}.metric b{display:block;font-size:17px}.metric span{font-size:12px;color:var(--muted)}.roiList{max-height:190px;overflow:auto;border:1px solid var(--line);border-radius:7px}.roiRow{display:grid;grid-template-columns:42px 1fr 52px;gap:6px;padding:6px 8px;border-bottom:1px solid #eef2f7;font-size:13px;cursor:pointer}.roiRow:hover,.roiRow.sel{background:#e0f2fe}.badge{font-size:11px;border-radius:5px;padding:1px 5px;background:#e2e8f0;color:#334155}.controls{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}.controls button{border:1px solid var(--line);background:white;border-radius:6px;padding:6px 9px}.controls button.active.accept{background:#dcfce7;border-color:#86efac}.controls button.active.reject{background:#fee2e2;border-color:#fca5a5}.controls button.active.unsure{background:#f3e8ff;border-color:#d8b4fe}#traceCanvas{width:100%;height:230px;border:1px solid var(--line);background:white;border-radius:7px}.hint{font-size:12px;color:var(--muted);line-height:1.35}.smallTable{width:100%;border-collapse:collapse;font-size:12px}.smallTable th,.smallTable td{border:1px solid var(--line);padding:5px;text-align:left}.smallTable th{background:#f1f5f9}.legend{display:flex;gap:10px;font-size:12px;color:var(--muted);flex-wrap:wrap}.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px}
</style>
</head>
<body>
<div class="app">
  <main class="stage">
    <h1>Interactive Neuron Review: calcium_video_2</h1>
    <div class="toolbar">
      <button id="playBtn">Play</button>
      <label>Frame <input id="frameSlider" type="range" min="1" max="260" value="1"></label>
      <b id="frameLabel">1</b>
      <label><input id="showRois" type="checkbox" checked> ROIs</label>
      <label><input id="showLabels" type="checkbox" checked> IDs</label>
      <label><input id="showEvents" type="checkbox" checked> event frames</label>
      <label>event z <input id="eventThreshold" type="range" min="1.2" max="5" step="0.1" value="2.4"> <span id="eventThresholdLabel">2.4</span></label>
      <label>Kalman gain <input id="kalmanGain" type="range" min="0.01" max="0.18" step="0.005" value="0.06"> <span id="kalmanGainLabel">0.060</span></label>
      <label>spike gain <input id="spikeGain" type="range" min="0" max="0.05" step="0.002" value="0.008"> <span id="spikeGainLabel">0.008</span></label>
    </div>
    <div class="viewerWrap">
      <img id="frameImg" alt="video frame">
      <canvas id="overlay"></canvas>
    </div>
    <div class="status" id="status"></div>
    <h2>Selected ROI Trace</h2>
    <canvas id="traceCanvas" width="820" height="230"></canvas>
    <div class="legend">
      <span><i class="dot" style="background:#2563eb"></i>dF/F</span>
      <span><i class="dot" style="background:#64748b"></i>Kalman baseline</span>
      <span><i class="dot" style="background:#f59e0b"></i>event z</span>
      <span><i class="dot" style="background:#facc15"></i>called event</span>
    </div>
  </main>
  <aside class="side">
    <h2>Dataset</h2>
    <div class="metricGrid">
      <div class="metric"><b id="roiCount"></b><span>candidate ROIs</span></div>
      <div class="metric"><b id="eventCount"></b><span>events at threshold</span></div>
      <div class="metric"><b id="acceptedCount"></b><span>accepted</span></div>
      <div class="metric"><b id="rejectedCount"></b><span>rejected</span></div>
    </div>
    <h2>Review</h2>
    <div class="controls">
      <button id="acceptBtn" class="accept">Accept</button>
      <button id="rejectBtn" class="reject">Reject</button>
      <button id="unsureBtn" class="unsure">Unsure</button>
      <button id="clearBtn">Clear</button>
      <button id="exportBtn">Export TSV</button>
    </div>
    <textarea id="notes" rows="4" style="width:100%;border:1px solid var(--line);border-radius:7px;padding:7px" placeholder="Notes for selected ROI"></textarea>
    <h2>ROIs</h2>
    <div class="toolbar" style="padding:0;margin:0 0 8px">
      <label>area >= <input id="minAreaFilter" type="range" min="0" max="260" step="1" value="0"> <span id="minAreaLabel">0</span></label>
      <label>events >= <input id="minEventsFilter" type="range" min="0" max="12" step="1" value="0"> <span id="minEventsLabel">0</span></label>
    </div>
    <div class="roiList" id="roiList"></div>
    <h2>Parameters</h2>
    <table class="smallTable" id="paramTable"></table>
    <p class="hint">Labels and notes are stored in this browser's localStorage. Use Export TSV to save review decisions. The denoiser is trace-level: it estimates slow baseline with a robust Kalman update and treats positive innovations as candidate firing events.</p>
  </aside>
</div>
<script id="review-data" type="application/json">__DATA_JSON__</script>
<script>
const data = JSON.parse(document.getElementById('review-data').textContent);
const img = document.getElementById('frameImg');
const overlay = document.getElementById('overlay');
const ctx = overlay.getContext('2d');
const slider = document.getElementById('frameSlider');
const frameLabel = document.getElementById('frameLabel');
const statusEl = document.getElementById('status');
const traceCanvas = document.getElementById('traceCanvas');
const traceCtx = traceCanvas.getContext('2d');
const storeKey = 'neuron-review-calcium-video-2';
let currentFrame = 1;
let selectedId = data.rois.length ? data.rois[0].id : null;
let playing = false;
let timer = null;
let review = JSON.parse(localStorage.getItem(storeKey) || '{}');

slider.max = data.video.frames;
document.getElementById('roiCount').textContent = data.rois.length;

function framePath(frame){ return data.video.framePattern.replace('%03d', String(frame).padStart(3, '0')); }
function selectedRoi(){ return data.rois.find(r => r.id === selectedId) || data.rois[0]; }
function threshold(){ return Number(document.getElementById('eventThreshold').value); }
function kalmanGain(){ return Number(document.getElementById('kalmanGain').value); }
function spikeGain(){ return Number(document.getElementById('spikeGain').value); }
function minAreaFilter(){ return Number(document.getElementById('minAreaFilter').value); }
function minEventsFilter(){ return Number(document.getElementById('minEventsFilter').value); }
function roiState(id){ return review[id] || {state:'', notes:''}; }
function saveReview(){ localStorage.setItem(storeKey, JSON.stringify(review)); updateCounts(); renderRoiList(); drawOverlay(); }
function median(arr){ const a = [...arr].sort((x,y)=>x-y); const m = Math.floor(a.length/2); return a.length % 2 ? a[m] : 0.5*(a[m-1]+a[m]); }
function madSigma(arr, center){ return Math.max(1e-6, 1.4826 * median(arr.map(v => Math.abs(v - center)))); }
function modeledTrace(roi){
  const gain = kalmanGain(), sgain = spikeGain();
  const center = median(roi.dffTrace);
  const sigma = madSigma(roi.dffTrace, center);
  let baseline = center;
  const baselineTrace = [], eventTrace = [], zTrace = [];
  for(const v of roi.dffTrace){
    const residual = v - baseline;
    let k = gain;
    if(residual > 2.5 * sigma) k = sgain;
    if(residual < -1.0 * sigma) k = Math.min(0.18, gain * 1.8);
    baseline += k * residual;
    baselineTrace.push(baseline);
    const ev = Math.max(0, v - baseline);
    eventTrace.push(ev);
    zTrace.push(ev / sigma);
  }
  return {baselineTrace, eventTrace, zTrace, sigma};
}
function eventFrames(roi){ const zt = modeledTrace(roi).zTrace; const th = threshold(); const out = []; for(let i=1;i<zt.length-1;i++){ if(zt[i] >= th && zt[i] >= zt[i-1] && zt[i] >= zt[i+1]) out.push(i+1); } return out; }
function eventNearFrame(roi, frame){ return eventFrames(roi).some(f => Math.abs(f - frame) <= 1); }
function visibleRois(){ return data.rois.filter(r => r.area >= minAreaFilter() && eventFrames(r).length >= minEventsFilter()); }

function resizeOverlay(){
  const rect = img.getBoundingClientRect();
  overlay.width = data.video.width;
  overlay.height = data.video.height;
  overlay.style.width = rect.width + 'px';
  overlay.style.height = rect.height + 'px';
  drawOverlay();
}

function drawOverlay(){
  ctx.clearRect(0,0,overlay.width,overlay.height);
  if(!document.getElementById('showRois').checked) return;
  const showLabels = document.getElementById('showLabels').checked;
  const showEvents = document.getElementById('showEvents').checked;
  for(const roi of visibleRois()){
    const st = roiState(roi.id).state;
    const isSel = roi.id === selectedId;
    const isEvent = showEvents && eventNearFrame(roi, currentFrame);
    let color = st === 'accept' ? '#16a34a' : st === 'reject' ? '#dc2626' : st === 'unsure' ? '#9333ea' : '#38bdf8';
    if(isEvent) color = '#facc15';
    ctx.globalAlpha = isSel ? 0.95 : 0.72;
    ctx.fillStyle = color;
    for(const p of roi.points){ ctx.fillRect(p[0], p[1], 1, 1); }
    ctx.globalAlpha = 1;
    ctx.strokeStyle = isSel ? '#ffffff' : color;
    ctx.lineWidth = isSel ? 2 : 1;
    const r = Math.max(4, Math.sqrt(roi.area / Math.PI) + 2);
    ctx.beginPath(); ctx.arc(roi.centroidX, roi.centroidY, r, 0, Math.PI*2); ctx.stroke();
    if(showLabels){
      ctx.font = '10px Arial';
      ctx.fillStyle = '#ffffff';
      ctx.strokeStyle = '#111827';
      ctx.lineWidth = 3;
      ctx.strokeText(String(roi.id), roi.centroidX + 5, roi.centroidY - 5);
      ctx.fillText(String(roi.id), roi.centroidX + 5, roi.centroidY - 5);
    }
  }
}

function drawTrace(){
  const roi = selectedRoi();
  const w = traceCanvas.width, h = traceCanvas.height;
  traceCtx.clearRect(0,0,w,h);
  traceCtx.fillStyle = '#fff'; traceCtx.fillRect(0,0,w,h);
  if(!roi) return;
  const pad = 28;
  const model = modeledTrace(roi);
  const traces = [roi.dffTrace, model.baselineTrace, model.zTrace.map(v => v * 0.05)];
  let vals = traces.flat();
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if(hi - lo < 1e-6){ hi = lo + 1; }
  function x(i){ return pad + i * (w - 2*pad) / (data.video.frames - 1); }
  function y(v){ return h - pad - (v - lo) * (h - 2*pad) / (hi - lo); }
  traceCtx.strokeStyle = '#e2e8f0'; traceCtx.lineWidth = 1;
  for(let k=0;k<5;k++){ const yy = pad + k*(h-2*pad)/4; traceCtx.beginPath(); traceCtx.moveTo(pad,yy); traceCtx.lineTo(w-pad,yy); traceCtx.stroke(); }
  const drawLine = (arr, color) => { traceCtx.strokeStyle=color; traceCtx.lineWidth=1.6; traceCtx.beginPath(); arr.forEach((v,i)=>{ if(i===0) traceCtx.moveTo(x(i),y(v)); else traceCtx.lineTo(x(i),y(v)); }); traceCtx.stroke(); };
  drawLine(roi.dffTrace, '#2563eb');
  drawLine(model.baselineTrace, '#64748b');
  drawLine(model.zTrace.map(v => v * 0.05), '#f59e0b');
  traceCtx.strokeStyle = '#ef4444'; traceCtx.lineWidth = 1;
  const xf = x(currentFrame - 1); traceCtx.beginPath(); traceCtx.moveTo(xf,pad); traceCtx.lineTo(xf,h-pad); traceCtx.stroke();
  traceCtx.fillStyle = '#facc15';
  for(const f of eventFrames(roi)){ traceCtx.beginPath(); traceCtx.arc(x(f-1), pad + 8, 3, 0, Math.PI*2); traceCtx.fill(); }
  traceCtx.fillStyle = '#0f172a'; traceCtx.font = '13px Arial';
  traceCtx.fillText(`ROI ${roi.id} | area ${roi.area} | noise sigma ${model.sigma.toFixed(5)} | events ${eventFrames(roi).length}`, pad, 18);
}

function setFrame(frame){
  currentFrame = Math.max(1, Math.min(data.video.frames, frame));
  slider.value = currentFrame; frameLabel.textContent = currentFrame;
  img.src = framePath(currentFrame);
  statusEl.textContent = `Frame ${currentFrame} / ${data.video.frames}`;
  drawTrace();
}

function renderRoiList(){
  const root = document.getElementById('roiList');
  root.innerHTML = '';
  for(const roi of visibleRois()){
    const row = document.createElement('div');
    row.className = 'roiRow' + (roi.id === selectedId ? ' sel' : '');
    const st = roiState(roi.id).state || 'new';
    row.innerHTML = `<b>#${roi.id}</b><span>${eventFrames(roi).length} events, area ${roi.area}</span><span class="badge">${st}</span>`;
    row.onclick = () => { selectedId = roi.id; document.getElementById('notes').value = roiState(roi.id).notes || ''; renderRoiList(); drawOverlay(); drawTrace(); };
    root.appendChild(row);
  }
}

function updateCounts(){
  let events = data.rois.reduce((sum, r) => sum + eventFrames(r).length, 0);
  let acc = 0, rej = 0;
  for(const r of data.rois){ const st = roiState(r.id).state; if(st === 'accept') acc++; if(st === 'reject') rej++; }
  document.getElementById('eventCount').textContent = events;
  document.getElementById('acceptedCount').textContent = acc;
  document.getElementById('rejectedCount').textContent = rej;
}

function setState(state){
  const roi = selectedRoi(); if(!roi) return;
  review[roi.id] = Object.assign(roiState(roi.id), {state});
  saveReview();
}

function exportTsv(){
  const rows = ['roi_id\tstate\tnotes\tcentroid_x\tcentroid_y\tarea\tevent_count\tnoise_sigma'];
  for(const roi of data.rois){
    const st = roiState(roi.id);
    const cleanNotes = (st.notes || '').split(String.fromCharCode(9)).join(' ').split(String.fromCharCode(10)).join(' ');
    rows.push([roi.id, st.state || '', cleanNotes, roi.centroidX, roi.centroidY, roi.area, eventFrames(roi).length, roi.noiseSigma].join('\t'));
  }
  const newline = String.fromCharCode(10);
  const blob = new Blob([rows.join(newline) + newline], {type:'text/tab-separated-values'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'neuron_review_labels.tsv';
  a.click();
  URL.revokeObjectURL(a.href);
}

function renderParams(){
  const table = document.getElementById('paramTable');
  table.innerHTML = '<tr><th>Parameter</th><th>Value</th></tr>' + Object.entries(data.parameters).map(([k,v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
}

slider.oninput = () => setFrame(Number(slider.value));
document.getElementById('playBtn').onclick = () => {
  playing = !playing;
  document.getElementById('playBtn').textContent = playing ? 'Pause' : 'Play';
  if(playing){ timer = setInterval(() => setFrame(currentFrame >= data.video.frames ? 1 : currentFrame + 1), 120); }
  else { clearInterval(timer); }
};
for(const id of ['showRois','showLabels','showEvents']) document.getElementById(id).onchange = drawOverlay;
document.getElementById('eventThreshold').oninput = e => { document.getElementById('eventThresholdLabel').textContent = e.target.value; updateCounts(); renderRoiList(); drawOverlay(); drawTrace(); };
document.getElementById('kalmanGain').oninput = e => { document.getElementById('kalmanGainLabel').textContent = Number(e.target.value).toFixed(3); updateCounts(); renderRoiList(); drawOverlay(); drawTrace(); };
document.getElementById('spikeGain').oninput = e => { document.getElementById('spikeGainLabel').textContent = Number(e.target.value).toFixed(3); updateCounts(); renderRoiList(); drawOverlay(); drawTrace(); };
document.getElementById('minAreaFilter').oninput = e => { document.getElementById('minAreaLabel').textContent = e.target.value; updateCounts(); renderRoiList(); drawOverlay(); };
document.getElementById('minEventsFilter').oninput = e => { document.getElementById('minEventsLabel').textContent = e.target.value; updateCounts(); renderRoiList(); drawOverlay(); };
document.getElementById('acceptBtn').onclick = () => setState('accept');
document.getElementById('rejectBtn').onclick = () => setState('reject');
document.getElementById('unsureBtn').onclick = () => setState('unsure');
document.getElementById('clearBtn').onclick = () => setState('');
document.getElementById('exportBtn').onclick = exportTsv;
document.getElementById('notes').oninput = e => { const roi = selectedRoi(); if(!roi) return; review[roi.id] = Object.assign(roiState(roi.id), {notes:e.target.value}); saveReview(); };
overlay.onclick = e => {
  const rect = overlay.getBoundingClientRect();
  const x = (e.clientX - rect.left) * data.video.width / rect.width;
  const y = (e.clientY - rect.top) * data.video.height / rect.height;
  let best = null, bestD = Infinity;
  for(const roi of visibleRois()){ const dx = x - roi.centroidX, dy = y - roi.centroidY, d = dx*dx + dy*dy; if(d < bestD){ bestD = d; best = roi; } }
  if(best){ selectedId = best.id; document.getElementById('notes').value = roiState(best.id).notes || ''; renderRoiList(); drawOverlay(); drawTrace(); }
};
img.onload = resizeOverlay;
window.onresize = resizeOverlay;
renderParams(); updateCounts(); renderRoiList(); setFrame(1); document.getElementById('notes').value = selectedRoi() ? roiState(selectedRoi().id).notes || '' : '';
</script>
</body>
</html>
'''

html = html.replace("__DATA_JSON__", dataJson.replace("</script>", "<\\/script>"))
Files.write(outputDir.resolve("index.html"), html.getBytes("UTF-8"))

rawImp.close()
zImp.close()
println("Done. Wrote interactive neuron review app to ${outputDir.resolve('index.html')}")
System.exit(0)
