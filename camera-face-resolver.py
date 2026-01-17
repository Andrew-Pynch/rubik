import cv2 

url = "http://192.168.1.237:8081/video"
cap = cv2.VideoCapture(url)

if not cap.isOpened():
    print("Cannot connect to stream")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Convert the frame to JPEG format for display
        _, buffer = cv2.imencode('.jpg', frame)

        # Display the image inline, clearing the previous one to 
        # simulate video
        # clear_output(wait=True)
        # display(Image(data=buffer.tobytes()))

except KeyboardInterrupt:
    cap.release()  
    print("Stream stopped")
